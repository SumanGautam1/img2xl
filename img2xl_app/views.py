# views.py
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.conf import settings
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd
# No more pdf2image!

# Configure GenAI (do this once)
try:
    genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
except AttributeError:
    print("ERROR: GOOGLE_GEMINI_API_KEY not found in Django settings.")
    pass
except Exception as e:
    print(f"Error configuring GenAI: {e}")
    pass

def extract_table_page(request):
    if request.method == "POST":
        action = request.POST.get('action', 'extract_text')

        # ACTION 1: Extract text from uploaded files (images or PDF)
        if action == 'extract_text':
            uploaded_files = request.FILES.getlist('image_files')

            if not uploaded_files:
                return JsonResponse({'success': False, 'error': 'No files provided.'}, status=400)

            all_csv_texts = []
            original_filename = uploaded_files[0].name

            try:
                # --- 1. Craft the Prompt for Gemini ---
                # This prompt now needs to be robust for both images and multi-page PDFs
                prompt_text = """
            You are a high-precision, automated data extraction engine. Your only function is to convert the primary table or list from a file into a pure, machine-parsable CSV string.

**Your Extraction Strategy:**

You must process the data using the following hierarchical strategy. Attempt Step 1 first. Only if it fails, proceed to Step 2.

**Step 1: The "Header-First" Method (Primary Strategy for PDFs & Formal Tables)**

1.  **Find a Header Row:** Scan the entire text for a single line that clearly functions as a table header. Headers typically contain words like "S.N.", "Item", "Description", "Quantity", "Rate", "Amount", "Price", etc.
2.  **Apply Strict Structure:** If a clear header row is identified:
    *   Use that line as your CSV header.
    *   Assume all subsequent lines that follow a consistent pattern are rows of that table. The number of columns is now strictly defined by this header.
    *   Extract every column found. Do not merge or simplify data.
    *   **Crucially, identify and discard any repeated header rows** that may appear in the middle of the data, which is a common issue from multi-page PDF extractions.

**Step 2: The "Flexible List" Method (Fallback for Handwriting & Simple Lists)**

*   **Condition:** Use this method **only if** you cannot identify a clear header row in Step 1.
*   **Action:** Look for a simple itemized list (e.g., lines starting with numbers like `1.`, `(2)`, or bullets).
*   **Structure:**
    *   Create a simple 2 or 3-column CSV with headers like "No.", "Description", and optionally "Details".
    *   Merge any inconsistent data (like quantities that only appear on some lines) into the "Description" column to maintain a valid CSV structure.

**Universal Formatting Rules (Apply to ALL Outputs):**

*   **IMPERATIVE Quoting Rule:** If any cell value contains a comma, the entire value **MUST** be enclosed in double quotes (`"`). This is the most critical rule for preventing parser failure.
    *   **Correct Example:** `1,"Item, with comma",100`
    *   **Incorrect Example:** `1,Item, with comma,100`
*   **Row Consistency:** Every row in the final CSV must have the exact same number of commas. Represent empty cells as an empty field (e.g., `value1,,value3`).
*   **Special Text:** Append ` [CROSSED_OUT]` to any text that is clearly struck-through.
*   **Ignore Noise:** Discard all unrelated text: page numbers, company logos, addresses, paragraphs, signatures, and marginalia.

**Final Output Requirements (Strictly Enforced):**

1.  **If Data Found:** Your response **must ONLY be the pure CSV string**.
2.  **If No Data Found:** Your response **must ONLY be the exact string: `NO_TABLE_FOUND`**.
3.  **DO NOT** include any explanations, summaries, or markdown formatting (like ` ```csv `).
            """
                model_name = "gemini-1.5-flash"
                model = genai.GenerativeModel(model_name)

                # --- 2. Loop Through All Uploaded Files ---
                for uploaded_file in uploaded_files:
                    file_mime_type = uploaded_file.content_type
                    
                    # --- 3. Prepare the File Part for Gemini ---
                    if 'pdf' not in file_mime_type and 'image' not in file_mime_type:
                        return JsonResponse({'success': False, 'error': f'Unsupported file type: {uploaded_file.name}'}, status=400)
                    
                    # Read file bytes and create the part for the API call
                    file_bytes = uploaded_file.read()
                    file_part = {"mime_type": file_mime_type, "data": file_bytes}
                    
                    # --- 4. Call Gemini API ---
                    response_gemini = model.generate_content([prompt_text, file_part])
                    extracted_text = response_gemini.text.strip()

                    if extracted_text and "NO_TABLE_FOUND" not in extracted_text:
                        all_csv_texts.append(extracted_text)

                # --- 5. Combine and Deduplicate CSV data ---
                if not all_csv_texts:
                    return JsonResponse({'success': True, 'message': 'No tables found in the uploaded files.', 'csv_text': ''})

                # Use pandas to read, concatenate, and deduplicate
                all_dfs = []
                for csv_text in all_csv_texts:
                    try:
                        # Use StringIO to treat the string as a file
                        df = pd.read_csv(io.StringIO(csv_text))
                        if not df.empty:
                            all_dfs.append(df)
                    except pd.errors.EmptyDataError:
                        continue # Ignore empty CSVs from Gemini

                if not all_dfs:
                    return JsonResponse({'success': True, 'message': 'Extracted data was empty or not valid.', 'csv_text': ''})

                combined_df = pd.concat(all_dfs, ignore_index=True)
                combined_df.drop_duplicates(inplace=True)

                final_csv_text = combined_df.to_csv(index=False)

                return JsonResponse({
                    'success': True,
                    'csv_text': final_csv_text,
                    'filename_base': original_filename
                })

            except Exception as e:
                print(f"Error during file processing: {e}")
                return JsonResponse({'success': False, 'error': f'An unexpected error occurred: {str(e)}'}, status=500)

        # ACTION 2: Generate Excel from provided CSV text
        # (This part of the code remains the same as before)
        elif action == 'download_excel':
            csv_text = request.POST.get('csv_data')
            filename_base = request.POST.get('filename_base', 'extracted_data')

            if not csv_text:
                return JsonResponse({'success': False, 'error': 'No CSV data provided for Excel generation.'}, status=400)

            try:
                csv_data_io = io.StringIO(csv_text)
                df = pd.read_csv(csv_data_io)

                if df.empty:
                    return JsonResponse({'success': False, 'error': 'CSV data resulted in an empty table.'}, status=400)

                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Sheet1')
                excel_buffer.seek(0)

                safe_filename_base = "".join(c if c.isalnum() or c in ('.', '_') else '_' for c in filename_base)
                safe_filename_base = ".".join(safe_filename_base.split('.')[:-1])

                response_excel = HttpResponse(
                    excel_buffer.getvalue(),
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response_excel['Content-Disposition'] = f'attachment; filename="{safe_filename_base}.xlsx"'
                excel_buffer.close()
                return response_excel

            except pd.errors.EmptyDataError:
                 return JsonResponse({'success': False, 'error': 'Provided CSV data for Excel was empty or not valid.'}, status=400)
            except Exception as e:
                print(f"Error generating Excel from text: {e}")
                return JsonResponse({'success': False, 'error': f'Error generating Excel file: {str(e)}'}, status=500)

        else:
            return JsonResponse({'success': False, 'error': 'Invalid action specified.'}, status=400)

    # For GET request, just show the upload page
    return render(request, 'extract_table.html')