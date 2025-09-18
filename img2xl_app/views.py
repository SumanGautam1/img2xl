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
Your primary goal is to identify and extract all structured tabular data from the provided file (image or PDF) and represent it as a single, consolidated CSV string.

**Core Task: Table Extraction**

1.  **Identify the Main Table:** Locate the primary table in the document. This table will typically have the most columns and define the main structure of the data.
2.  **Extract Base Data:** Extract all rows and columns from this main table. Infer sensible headers based on the content (e.g., "S.N.", "Description", "Specification", "Quantity", "Basic Rate").

**Special Rule for Split Tables (Multi-Page PDFs):**
This is the most important rule. A single table may be split across pages.
*   After extracting the main table from a page (e.g., Page 1), **immediately inspect the next page (e.g., Page 2)**.
*   Look for columns of data that are vertically aligned.
*   **Crucially, check if the number of rows in the column on the new page matches the number of rows you just extracted from the main table.**
*   If they match, assume it is a continuation of the table. Use the heading above this column (e.g., "Total") as its new header and **append this data as a new column to the rows of the main table.**
*   Ignore any final summary/total rows at the very bottom of a continuation column that don't align with a specific data row (like a grand total for the whole column).

**Formatting and Output Rules:**

3.  **Create a Single Header:** Your final output MUST begin with a single header row. This header should include columns from the main table AND any columns you appended from subsequent pages.
4.  **Format as CSV:**
    *   Combine all data into a single CSV block under the one header.
    *   Values should be separated by a single comma. Enclose values in double quotes if they contain a comma.
    *   Ensure all rows have the same number of commas (i.e., the same number of columns as the header).
5.  **No Table Case:** If the file contains no discernible list or tabular data, respond with the exact text: "NO_TABLE_FOUND".
6.  **Output Purity:** Your response must ONLY be the CSV data or the "NO_TABLE_FOUND" string. Do not include any explanations, markdown, or other text.

**Example Scenario:**
*   **Page 1 has a table:** "S.N.", "Item", "Quantity", "Price" with 20 rows.
*   **Page 2 has a single column:** Headed "Total", with 20 corresponding values.
*   **Your action:** Extract the Page 1 table. See that the Page 2 column has 20 rows. Merge them.
*   **Expected CSV Output:**
    S.N.,Item,Quantity,Price,Total
    1,"Apples",10,2.00,20.00
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