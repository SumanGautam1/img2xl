# views.py
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.conf import settings
import google.generativeai as genai
from PIL import Image
import io
import pandas as pd # For creating DataFrame and Excel

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
        image_file = request.FILES.get('image_file')

        if not image_file:
            return render(request, 'extract_table.html', {'error': 'No image file provided.'})

        try:
            # --- 1. Prepare Image for Gemini ---
            img = Image.open(image_file)
            img.verify() # Verify it's an image
            image_file.seek(0) # Reset file pointer after verify
            
            mime_type = image_file.content_type
            if not mime_type or not mime_type.startswith('image/'):
                return render(request, 'extract_table.html', {'error': 'Uploaded file is not a valid image.'})

            image_bytes = image_file.read()
            image_part = {"mime_type": mime_type, "data": image_bytes}

            # --- 2. Craft the Prompt for Gemini ---
            # This prompt is crucial for getting structured output.
            # Experiment with this prompt for best results.
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
            model_name = "gemini-1.5-flash" # Or "gemini-pro-vision"
            model = genai.GenerativeModel(model_name)
            
            response = model.generate_content([prompt_text, image_part])
            extracted_text = response.text.strip()

            # --- 4. Process Gemini's Response ---
            if not extracted_text or "NO_TABLE_FOUND" in extracted_text:
                return render(request, 'extract_table.html', {'message': 'No table found in the image or data could not be extracted.'})

            # --- 5. Convert CSV text to Pandas DataFrame ---
            # Use io.StringIO to treat the string as a file
            try:
                csv_data = io.StringIO(extracted_text)
                df = pd.read_csv(csv_data) # Pandas is great at parsing CSV
            except pd.errors.EmptyDataError:
                 return render(request, 'extract_table.html', {'error': 'Extracted data was empty or not valid CSV.'})
            except Exception as e: # Catch other pandas parsing errors
                 return render(request, 'extract_table.html', {'error': f'Error parsing extracted table data: {str(e)}\nRaw data: {extracted_text}'})


            if df.empty:
                return render(request, 'extract_table.html', {'message': 'Extracted table is empty.'})

            # --- 6. Create Excel file in memory ---
            excel_buffer = io.BytesIO()
            # Use a try-except block for the Excel writing process
            try:
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Sheet1')
                # writer is automatically saved and closed when exiting the 'with' block
                excel_buffer.seek(0) # Reset buffer's pointer to the beginning
            except Exception as e:
                return render(request, 'extract_table.html', {'error': f'Error generating Excel file: {str(e)}'})

            # --- 7. Serve Excel file for download ---
            response_excel = HttpResponse(
                excel_buffer.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response_excel['Content-Disposition'] = f'attachment; filename="extracted_table_{image_file.name}.xlsx"'
            
            # Clean up buffer
            excel_buffer.close()
            
            return response_excel

        except Exception as e:
            # General error handling
            print(f"Error during table extraction: {e}") # Log for debugging
            return render(request, 'extract_table.html', {'error': f'An unexpected error occurred: {str(e)}'})

    # For GET request, just show the upload page
    return render(request, 'extract_table.html')