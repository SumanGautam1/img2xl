# Django Image to Excel Generator

## Description
This is a image to excel Generator made using Django and Bootstrap. It can easily generate excel file for images with proper structure and clarity. It can also recognise handwriting to some extent but not 100% accurate. The primary purpose of this project is to help people save time manually typing data from images to excelsheet. It uses Gemini 1.5 flash model to extract the data in proper format and uses python libraries to generate a downloadable excel file. It also provides the extracted CSV data in case the excel file is not generated properly. You can modify the prompt as you see fit to handle the types of image data.

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/SumanGautam1/VehicleRentalSystem.git

2. Install the dependencies:
    ```bash
    pip install -r requirements.txt

3. Create a ```.env``` file in your root directory and configure your ```DJANGO_SECRET_KEY, GOOGLE_GEMINI_API_KEY```.
    You can generate a secure key using:
    ```bash
    python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

You can get the GOOGLE_GEMINI_API_KEY from [official documentation](https://ai.google.dev/gemini-api/docs/pricing).
You can use advanced models as well which obviously work better but for simple use case, flash 1.5 is perfect since it is free for personal use and works fine.

4. Run migrations:
    ```bash
    python manage.py migrate
    python manage.py makemigrations

5. Start the development server:
    ```bash
    python manage.py runserver

## UI Screenshots:
### Home Page
![Home Page](assets/homepage.png?raw=true "Home Page")

### Demo 1
<table>
<tr>
<td align="center">
<img src="assets/1.jpg?raw=true" alt="Proper Tabular Image" title="Tabular Image" width="350">
<br><em>Proper Tabular Image</em>
</td>
<td align="center">
<img src="assets/1.png?raw=true" alt="Result 1" title="Tabular Excel" width="350">
<br><em>Result 1 (Tabular Excel)</em>
</td>
</tr>
</table>

### Demo 2
<table>
<tr>
<td align="center">
<img src="assets/handwriting.jpg?raw=true" alt="Handwriting Data" title="Handwriting Data" width="350">
<br><em>Handwriting Data</em>
</td>
<td align="center">
<img src="assets/2.png?raw=true" alt="Result 2" title="Excel" width="350">
<br><em>Result 2 (Excel)</em>
</td>
</tr>
</table>