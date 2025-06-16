# views.py
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.conf import settings
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd

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
        action = request.POST.get('action', 'extract_text') # Default action

        # ACTION 1: Extract text from image
        if action == 'extract_text':
            image_file = request.FILES.get('image_file')

            if not image_file:
                return JsonResponse({'success': False, 'error': 'No image file provided.'}, status=400)

            try:
                # --- 1. Prepare Image for Gemini ---
                try:
                    img = Image.open(image_file)
                    img.verify() # Verify it's an image
                    image_file.seek(0) # Reset file pointer after verify
                except Exception as img_e:
                    return JsonResponse({'success': False, 'error': f'Invalid image file: {str(img_e)}'}, status=400)

                mime_type = image_file.content_type
                if not mime_type or not mime_type.startswith('image/'):
                    return JsonResponse({'success': False, 'error': 'Uploaded file is not a valid image type.'}, status=400)

                image_bytes = image_file.read()
                image_part = {"mime_type": mime_type, "data": image_bytes}

                # --- 2. Craft the Prompt for Gemini (Your existing prompt) ---
                prompt_text = """
                Your primary goal is to identify and extract structured list or tabular data from the image and represent it as a CSV string.
                Focus on lists that have clear itemization (e.g., numbers, bullets) or visual column-like arrangements, even if handwritten.
    
                1.  **Identify Main Data Block:** Locate the primary list or table in the image. Try to ignore surrounding annotations or unrelated text if they are not part of this main data structure. For example, text at the very top or bottom that isn't part of the itemized list should generally be excluded from the CSV.
                2.  **Infer Columns:**
                    *   For lists with explicit numbering (e.g., 1., 2., (1), (a)), this numbering should form the first column.
                    *   The main descriptive text for each item should be the next column.
                    *   If other consistent pieces of information appear alongside each item (e.g., quantities like "3ml", "500 mg", units, brief notes), try to parse these into subsequent columns. If this information is not consistently present or clearly separable, it can be part of the main description.
                3.  **Create Headers:** The first line of your CSV output MUST be a header row.
                    Infer sensible column headers based on the content. Examples: "Index", "Item Description", "Details", "Quantity". For a simple numbered list from the image, "No.", "Item" or "No.", "Description", "Details" might be suitable.
                4.  **Handle Crossed-Out Items:** If items are clearly crossed out, you may choose to either omit them or include them with a note indicating they are crossed out (e.g., in a 'Status' column or appended to the description like "[CROSSED_OUT]"). For simplicity in initial extraction, including them as read might be acceptable.
                5.  **Format as CSV:**
                    *   Each identified row from the image's main data block should become a new line in the CSV.
                    *   Values within a row should be separated by a single comma.
                    *   If a value itself contains a comma, enclose that value in double quotes (e.g., "value, with comma").
                    *   If a column is empty for a particular row, represent it as an empty field (e.g., value1,,value3). Ensure all rows have the same number of commas (i.e., same number of columns as defined by your header row).
                6.  **No Table Case:** If the image does not contain any discernible list or tabular data that can be reasonably converted to CSV, or if the list is too sparse/irregular, respond with the exact text: "NO_TABLE_FOUND".
                7.  **Output Purity:** Your response must ONLY be the CSV data or the "NO_TABLE_FOUND" string. Do not include any other explanations, markdown formatting, or introductory/concluding remarks.
    
                Example for a numbered list with some details:
                Image might show:
                My Shopping List
                (1) Apples - 5 pcs, red
                (2) Milk (low fat)
                (3) Bread
    
                Expected CSV output (ignoring "My Shopping List"):
                No.,Item,Details
                1,"Apples","5 pcs, red"
                2,"Milk (low fat)",""
                3,"Bread",""
                """

                # --- 3. Call Gemini API ---
                model_name = "gemini-1.5-flash"
                model = genai.GenerativeModel(model_name)
                response_gemini = model.generate_content([prompt_text, image_part])
                extracted_text = response_gemini.text.strip()

                # --- 4. Process Gemini's Response ---
                if not extracted_text or "NO_TABLE_FOUND" in extracted_text:
                    return JsonResponse({'success': True, 'message': 'No table found in the image or data could not be extracted.', 'csv_text': ''})

                # --- 5. Validate CSV structure (optional but good) ---
                try:
                    pd.read_csv(io.StringIO(extracted_text))
                except pd.errors.EmptyDataError:
                    return JsonResponse({'success': False, 'error': 'Extracted data was empty or not valid CSV. Gemini Output: ' + extracted_text}, status=400)
                except Exception as e:
                    return JsonResponse({'success': False, 'error': f'Error parsing extracted table data: {str(e)}\nRaw data from Gemini: {extracted_text}'}, status=400)

                return JsonResponse({
                    'success': True,
                    'csv_text': extracted_text,
                    'filename_base': image_file.name
                })

            except Exception as e:
                print(f"Error during table extraction: {e}")
                return JsonResponse({'success': False, 'error': f'An unexpected error occurred: {str(e)}'}, status=500)

        # ACTION 2: Generate Excel from provided CSV text
        elif action == 'download_excel':
            csv_text = request.POST.get('csv_data')
            filename_base = request.POST.get('filename_base', 'extracted_data')

            if not csv_text:
                return JsonResponse({'success': False, 'error': 'No CSV data provided for Excel generation.'}, status=400)

            try:
                csv_data_io = io.StringIO(csv_text)
                df = pd.read_csv(csv_data_io)

                if df.empty:
                    # This case should ideally be caught by the CSV validation on extraction
                    # but good to have a check here too.
                    return JsonResponse({'success': False, 'error': 'CSV data resulted in an empty table.'}, status=400)

                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Sheet1')
                excel_buffer.seek(0)

                safe_filename_base = "".join(c if c.isalnum() or c in ('.', '_') else '_' for c in filename_base)
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