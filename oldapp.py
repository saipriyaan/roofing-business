import os
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import uuid
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure secret key

# MongoDB Configuration
client = MongoClient('mongodb+srv://sai:8778386853@cluster0.9vhjs.mongodb.net/quotbusiness?retryWrites=true&w=majority&appName=Cluster0')
db = client['quote_calculator']
quotes_collection = db['quotes']
users_collection = db['users']
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
MAIL_USERNAME='serviceemailshop@gmail.com'
MAIL_PASSWORD='ukdqyqjvqepfeuad'
ADMIN_EMAIL='expenditure.cob@gmail.com'

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = "serviceemailshop@gmail.com"
app.config['MAIL_PASSWORD'] = "ukdqyqjvqepfeuad"
app.config['MAIL_DEFAULT_SENDER'] = "serviceemailshop@gmail.com"  # Add this line

# Google Drive Configuration
SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'cred.json'

# Pricing Data (hardcoded from your Excel)
PRICES = {
    'Dakbedekking': {
        'bitumen_plat': {'price': 55.0, 'label': 'Bitumen dakbedekking (plat dak)'},
        'epdm_plat': {'price': 65.0, 'label': 'EPDM dakbedekking (plat dak)'},
        'pvc_plat': {'price': 60.0, 'label': 'PVC dakbedekking (plat dak)'},
        'pannen_hellend': {'price': 85.0, 'label': 'Dakpannen (hellend dak)'},
        'leien_kunststof': {'price': 75.0, 'label': 'Kunststof leien dakbedekking'},
        'leien_natuursteen': {'price': 125.0, 'label': 'Natuurstenen leien dakbedekking'},
        'zink_hellend': {'price': 110.0, 'label': 'Zinken dakbedekking (hellend dak)'},
    },
    'Verwijderen': {
        'verwijder_bitumen': {'price': 15.0, 'label': 'Verwijderen oude bitumen dakbedekking'},
        'verwijder_epdm': {'price': 15.0, 'label': 'Verwijderen oude EPDM dakbedekking'},
        'verwijder_pannen': {'price': 18.0, 'label': 'Verwijderen oude dakpannen'},
        'verwijder_leien': {'price': 20.0, 'label': 'Verwijderen oude leien dakbedekking'},
        'verwijder_zink': {'price': 20.0, 'label': 'Verwijderen oude zinken dakbedekking'},
    },
    'Isolatie': {
        'isolatie_binnen': {'price': 60.0, 'label': 'Isolatie aan binnenzijde van het dak'},
        'isolatie_buiten': {'price': 120.0, 'label': 'Isolatie aan buitenzijde van het dak'},
    },
    'Reparatie': {
        'reparatie_klein': {'price': 250.0, 'label': 'Reparatie van kleine lekkage'},
        'reparatie_groot': {'price': 1250.0, 'label': 'Grote dakreparatie of constructieschade'},
    },
    'Extra': {
        'extra_dakkapel': {'price': 150.0, 'label': 'Meerprijs dakkapel'},
        'extra_dakraam': {'price': 120.0, 'label': 'Meerprijs dakraam'},
        'extra_schoorsteen': {'price': 100.0, 'label': 'Meerprijs schoorsteen'},
        'extra_ventilatie': {'price': 50.0, 'label': 'Meerprijs ventilatiepijp'},
        'extra_zonnepanelen': {'price': 300.0, 'label': 'Verplaatsen zonnepanelen'},
    },
    'Voorrijkosten': {
        'voorrijden_0_30': {'price': 0.0, 'label': 'Voorrijkosten (binnen 30 km)'},
        'voorrijden_30_60': {'price': 45.0, 'label': 'Voorrijkosten (30–60 km)'},
        'voorrijden_60_plus': {'price': 75.0, 'label': 'Voorrijkosten (meer dan 60 km)'},
    },
    'Staffelkorting': {
        'korting_50m2': {'price': -0.05, 'label': 'Staffelkorting vanaf 50 m²'},
        'korting_100m2': {'price': -0.1, 'label': 'Staffelkorting vanaf 100 m²'},
    }
}

# Form Flow Logic
FORM_FLOW = [
    {
        'step': 1,
        'question': 'Wat voor werk wilt u laten uitvoeren?',
        'type': 'multi',
        'options': ['Nieuw dak', 'Dakrenovatie', 'Reparatie', 'Isolatie', 'Inspectie'],
        'next_step': 2,
        'logic': {
            'Reparatie': 7  # Shows damage question if Reparatie is selected
        }
    },
     {
        'step': 2,
        'question': 'Wat voor dak heeft u?',
        'type': 'single',
        'options': ['Plat dak', 'Hellend dak', 'Beide', 'Weet ik niet'],
        'next_step': 3,
        'logic': {
            'Plat dak': {'filter': ['Bitumen', 'EPDM', 'PVC'], 'next_step': 3},
            'Hellend dak': {'filter': ['Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink'], 'next_step': 3}
        }
    },
    {
        'step': 3,
        'question': 'Wat is de huidige dakbedekking?',
        'type': 'single',
        'options': ['Bitumen', 'EPDM', 'PVC', 'Dakpannen', 'Leien', 'Zink', 'Weet ik niet'],
        'next_step': 4
    },
    {
        'step': 4,
        'question': 'Wat is de gewenste nieuwe dakbedekking?',
        'type': 'single',
        'options': ['Bitumen', 'EPDM', 'PVC', 'Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Geen voorkeur'],
        'next_step': 5
    },
    {
        'step': 5,
        'question': 'Hoeveel m² betreft het?',
        'type': 'input',
        'next_step': 6,
        'logic': {
            'empty': {'show_upload': True}
        }
    },
    {
        'step': 6,
        'question': 'Wat is de staat van het huidige dak?',
        'type': 'single',
        'options': ['Goed', 'Verouderd', 'Slecht of beschadigd', 'Nieuwbouw'],
        'next_step': 8,  # Default next step
        'logic': {
            'Slecht of beschadigd': 7  # Shows damage question
        }
    },
    {
        'step': 7,
        'question': 'Wat is de aard van de schade?',
        'type': 'single',
        'options': ['Lekkage', 'Losse dakbedekking', 'Constructieproblemen', 'Anders'],
        'next_step': 8
    },
    {
        'step': 8,
        'question': 'Moet de huidige dakbedekking verwijderd worden?',
        'type': 'single',
        'options': ['Ja', 'Nee', 'Weet ik niet'],
        'next_step': 9
    },
    {
        'step': 9,
        'question': 'Zijn er extra elementen aanwezig op het dak?',
        'type': 'multi',
        'options': ['Dakkapel', 'Dakraam', 'Schoorsteen', 'Ventilatiepijp', 'Zonnepanelen', 'Geen'],
        'next_step': 10
    },
    {
        'step': 10,
        'question': 'Wat is de huidige isolatie?',
        'type': 'single',
        'options': ['Geen', 'Binnenzijde', 'Buitenzijde', 'Weet ik niet'],
        'next_step': 11
    },
    {
        'step': 11,
        'question': 'Adres van de woning',
        'type': 'input',
        'next_step': 12
    },
    {
        'step': 12,
        'question': 'Uw gegevens',
        'type': 'input-group',
        'fields': ['Naam', 'Telefoonnummer', 'E-mailadres'],
        'next_step': 13
    },
    {
        'step': 13,
        'question': 'Opmerkingen of bijzonderheden',
        'type': 'textarea',
        'next_step': 14
    },
    {
        'step': 14,
        'question': 'Upload foto\'s of documenten',
        'type': 'upload',
        'next_step': 15
    },
    {
        'step': 15,
        'question': 'Wilt u direct een richtprijs ontvangen?',
        'type': 'single',
        'options': ['Toon op scherm', 'Mail mij de richtprijs', 'Alleen contact opnemen'],
        'next_step': None  # Final step
    }
]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'current_step' not in session:
        session['current_step'] = 1
        session['form_data'] = {}
        session['quote_id'] = str(uuid.uuid4())
    
    # Check if user has saved progress
    if 'email' in request.args:
        user_email = request.args.get('email')
        user_data = users_collection.find_one({'email': user_email})
        if user_data:
            session['current_step'] = user_data['current_step']
            session['form_data'] = user_data['form_data']
            session['quote_id'] = user_data['quote_id']
            return redirect(url_for('form_step', step=session['current_step']))
    
    return redirect(url_for('form_step', step=session['current_step']))

@app.route('/form/step/<int:step>', methods=['GET', 'POST'])
def form_step(step):
    if request.method == 'POST':
        # Handle form submission
        current_question = FORM_FLOW[step-1]
        field_name = current_question.get('question', '').replace(' ', '_').lower()
        
        if current_question['type'] == 'input-group':
            for field in current_question['fields']:
                session['form_data'][field] = request.form.get(field, '')
                if field == 'E-mailadres':
                    session['email'] = request.form.get(field, '')
        elif current_question['type'] == 'upload':
            if 'file' in request.files:
                file = request.files['file']
                if file.filename != '':
                    filename = secure_filename(file.filename)
                    upload_path = os.path.join('uploads', filename)
                    file.save(upload_path)
                    
                    try:
                        drive_service = get_drive_service()
                        file_metadata = {
                            'name': filename,
                            'parents': [create_quote_folder(session['quote_id'])]
                        }
                        media = MediaFileUpload(upload_path, mimetype=file.content_type)
                        uploaded_file = drive_service.files().create(
                            body=file_metadata,
                            media=media,
                            fields='id,webViewLink'
                        ).execute()
                        
                        session['form_data']['uploaded_files'] = session['form_data'].get('uploaded_files', [])
                        session['form_data']['uploaded_files'].append({
                            'name': filename,
                            'url': uploaded_file.get('webViewLink', '#')
                        })
                    except Exception as e:
                        print(f"Error uploading to Google Drive: {e}")
        else:
            session['form_data'][field_name] = request.form.get(field_name, '')
        
        # Save progress to MongoDB
        save_user_progress()
        
        # Determine next step based on logic
        next_step = current_question['next_step']
        
        # Check for conditional logic
        if 'logic' in current_question:
            if current_question['type'] in ['single', 'multi']:
                answer = request.form.get(field_name, '')
                if answer in current_question['logic']:
                    logic_result = current_question['logic'][answer]
                    if isinstance(logic_result, dict):
                        # For cases where we have filter logic
                        next_step = logic_result.get('next_step', next_step)
                    else:
                        # For simple step numbers
                        next_step = logic_result
        
        if next_step:
            session['current_step'] = next_step
            return redirect(url_for('form_step', step=next_step))
        else:
            # Final step - calculate quote
            return redirect(url_for('generate_quote'))
    
    # Handle GET request
    if step < 1 or step > len(FORM_FLOW):
        return redirect(url_for('index'))
    
    current_question = FORM_FLOW[step-1]
    
    # Apply any filtering logic for options
    filtered_question = current_question.copy()
    if 'logic' in current_question and session.get('form_data'):
        previous_answer = None
        # Check if we have a previous answer that affects this question
        if step == 3:  # Current dakbedekking question
            dak_type = session['form_data'].get('wat_voor_dak_heeft_u?', '')
            if dak_type in current_question['logic']:
                filter_options = current_question['logic'][dak_type]['filter']
                filtered_question['options'] = [opt for opt in current_question['options'] if opt in filter_options or opt == 'Weet ik niet']
    
    

    return render_template('newindex.html', 
                         question=filtered_question, 
                         step=step,  # Make sure this is an integer
                         total_steps=len(FORM_FLOW),  # Make sure this is an integer
                         form_data=session.get('form_data', {}))

def save_user_progress():
    if 'email' in session:
        user_data = {
            'email': session['email'],
            'current_step': session['current_step'],
            'form_data': session['form_data'],
            'quote_id': session['quote_id'],
            'last_updated': datetime.now()
        }
        users_collection.update_one(
            {'email': session['email']},
            {'$set': user_data},
            upsert=True
        )

def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'cred.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return build('drive', 'v3', credentials=creds)

def create_quote_folder(quote_id):
    drive_service = get_drive_service()
    folder_metadata = {
        'name': f'Quote_{quote_id}',
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': ['root']  # Change to your desired parent folder ID
    }
    folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')

def calculate_quote(form_data):
    total = 0
    items = []
    
    # Get basic information
    dak_type = form_data.get('wat_voor_dak_heeft_u?', '')
    werk_type = form_data.get('wat_voor_werk_wilt_u_laten_uitvoeren?', '')
    if isinstance(werk_type, str):
        werk_type = [werk_type]
    
    gewenste_dakbedekking = form_data.get('wat_is_de_gewenste_nieuwe_dakbedekking?', '')
    try:
        oppervlakte = float(form_data.get('hoeveel_m²_betreft_het?', 0))
    except:
        oppervlakte = 0
    
    # Calculate roof covering cost if it's new or renovation
    if 'Nieuw dak' in werk_type or 'Dakrenovatie' in werk_type:
        if dak_type == 'Plat dak':
            if gewenste_dakbedekking == 'Bitumen':
                item = PRICES['Dakbedekking']['bitumen_plat']
            elif gewenste_dakbedekking == 'EPDM':
                item = PRICES['Dakbedekking']['epdm_plat']
            elif gewenste_dakbedekking == 'PVC':
                item = PRICES['Dakbedekking']['pvc_plat']
        elif dak_type == 'Hellend dak':
            if gewenste_dakbedekking == 'Dakpannen':
                item = PRICES['Dakbedekking']['pannen_hellend']
            elif gewenste_dakbedekking == 'Leien (kunststof)':
                item = PRICES['Dakbedekking']['leien_kunststof']
            elif gewenste_dakbedekking == 'Leien (natuursteen)':
                item = PRICES['Dakbedekking']['leien_natuursteen']
            elif gewenste_dakbedekking == 'Zink':
                item = PRICES['Dakbedekking']['zink_hellend']
        
        if 'item' in locals():
            cost = item['price'] * oppervlakte
            items.append({
                'description': item['label'],
                'quantity': oppervlakte,
                'unit_price': item['price'],
                'total': cost
            })
            total += cost
    
    # Calculate removal cost if needed
    if form_data.get('moet_de_huidige_dakbedekking_verwijderd_worden?', '') == 'Ja':
        huidige_dakbedekking = form_data.get('wat_is_de_huidige_dakbedekking?', '')
        if huidige_dakbedekking == 'Bitumen':
            item = PRICES['Verwijderen']['verwijder_bitumen']
        elif huidige_dakbedekking == 'EPDM':
            item = PRICES['Verwijderen']['verwijder_epdm']
        elif huidige_dakbedekking == 'Dakpannen':
            item = PRICES['Verwijderen']['verwijder_pannen']
        elif huidige_dakbedekking == 'Leien':
            item = PRICES['Verwijderen']['verwijder_leien']
        elif huidige_dakbedekking == 'Zink':
            item = PRICES['Verwijderen']['verwijder_zink']
        
        if item:
            cost = item['price'] * oppervlakte
            items.append({
                'description': item['label'],
                'quantity': oppervlakte,
                'unit_price': item['price'],
                'total': cost
            })
            total += cost
    
    # Calculate insulation cost
    isolatie = form_data.get('wat_is_de_huidige_isolatie?', '')
    if isolatie == 'Binnenzijde':
        item = PRICES['Isolatie']['isolatie_binnen']
    elif isolatie == 'Buitenzijde':

        item = PRICES['Isolatie']['isolatie_buiten']
    
    if item:
        cost = item['price'] * oppervlakte
        items.append({
            'description': item['label'],
            'quantity': oppervlakte,
            'unit_price': item['price'],
            'total': cost
        })
        total += cost
    
    # Calculate repair costs if applicable
    if 'Reparatie' in form_data.get('wat_voor_werk_wilt_u_laten_uitvoeren?', []):
        schade = form_data.get('wat_is_de_aard_van_de_schade?', '')
        if schade == 'Lekkage':
            item = PRICES['Reparatie']['reparatie_klein']
        elif schade in ['Losse dakbedekking', 'Constructieproblemen', 'Anders']:
            item = PRICES['Reparatie']['reparatie_groot']
        
        if item:
            items.append({
                'description': item['label'],
                'quantity': 1,
                'unit_price': item['price'],
                'total': item['price']
            })
            total += item['price']
    
    # Calculate extra elements
    extra_elementen = form_data.get('zijn_er_extra_elementen_aanwezig_op_het_dak?', [])
    if isinstance(extra_elementen, str):
        extra_elementen = [extra_elementen]
    
    for element in extra_elementen:
        if element == 'Dakkapel':
            item = PRICES['Extra']['extra_dakkapel']
        elif element == 'Dakraam':
            item = PRICES['Extra']['extra_dakraam']
        elif element == 'Schoorsteen':
            item = PRICES['Extra']['extra_schoorsteen']
        elif element == 'Ventilatiepijp':
            item = PRICES['Extra']['extra_ventilatie']
        elif element == 'Zonnepanelen':
            item = PRICES['Extra']['extra_zonnepanelen']
        
        if item:
            items.append({
                'description': item['label'],
                'quantity': 1,
                'unit_price': item['price'],
                'total': item['price']
            })
            total += item['price']
    
    # Apply volume discount
    if oppervlakte >= 100:
        discount = PRICES['Staffelkorting']['korting_100m2']['price']
        discount_label = PRICES['Staffelkorting']['korting_100m2']['label']
    elif oppervlakte >= 50:
        discount = PRICES['Staffelkorting']['korting_50m2']['price']
        discount_label = PRICES['Staffelkorting']['korting_50m2']['label']
    else:
        discount = 0
        discount_label = ''
    
    if discount:
        discount_amount = total * discount
        items.append({
            'description': discount_label,
            'quantity': 1,
            'unit_price': discount_amount,
            'total': discount_amount
        })
        total += discount_amount  # Adding negative amount
    
    # Add travel costs (simplified for example)
    items.append({
        'description': 'Voorrijkosten (standaard)',
        'quantity': 1,
        'unit_price': 0,
        'total': 0
    })
    
    return {
        'items': items,
        'subtotal': total,
        'tax': total * 0.21,  # 21% VAT
        'total': total * 1.21
    }

@app.route('/generate-quote')
def generate_quote():
    if 'form_data' not in session:
        return redirect(url_for('index'))
    
    form_data = session['form_data']
    quote = calculate_quote(form_data)
    ontvangst_voorkeur = form_data.get('wilt_u_direct_een_richtprijs_ontvangen?', '')
    
    return render_template('nindex.html',
                         show_quote=True,
                         quote=quote,
                         form_data=form_data,
                         ontvangst_voorkeur=ontvangst_voorkeur)
def send_admin_notification(quote_data):
    try:
        msg = MIMEMultipart()
        msg['From'] = 'servies'
        msg['To'] = ADMIN_EMAIL
        msg['Subject'] = f'Nieuwe offerte aanvraag - {quote_data["quote_id"]}'
        
        body = f"""
        Er is een nieuwe offerte aanvraag binnengekomen:
        
        Offerte ID: {quote_data["quote_id"]}
        Naam: {quote_data["form_data"].get("Naam", "Onbekend")}
        E-mail: {quote_data["form_data"].get("E-mailadres", "Onbekend")}
        Telefoon: {quote_data["form_data"].get("Telefoonnummer", "Onbekend")}
        
        Totaalbedrag: €{quote_data["quote_details"]["total"]:,.2f}
        
        Details:
        {generate_quote_text(quote_data)}
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Error sending admin notification: {e}")

def send_quote_to_client(quote_data):
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_USERNAME
        msg['To'] = quote_data["form_data"].get("E-mailadres", "")
        msg['Subject'] = f'Uw offerte - {quote_data["quote_id"]}'
        
        body = f"""
        Beste {quote_data["form_data"].get("Naam", "klant")},
        
        Hierbij ontvangt u de offerte zoals aangevraagd via onze website.
        
        Offerte ID: {quote_data["quote_id"]}
        Datum: {datetime.now().strftime("%d-%m-%Y")}
        
        Details:
        {generate_quote_text(quote_data)}
        
        Met vriendelijke groet,
        Het team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"Error sending quote to client: {e}")

def generate_quote_text(quote_data):
    text = ""
    for item in quote_data['quote_details']['items']:
        text += f"{item['description']}: {item['quantity']} x €{item['unit_price']:,.2f} = €{item['total']:,.2f}\n"
    
    text += f"\nSubtotaal: €{quote_data['quote_details']['subtotal']:,.2f}\n"
    text += f"BTW (21%): €{quote_data['quote_details']['tax']:,.2f}\n"
    text += f"Totaal: €{quote_data['quote_details']['total']:,.2f}\n"
    return text

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # In a real app, use proper authentication with hashed passwords
        if username == 'admin' and password == 'admin123':  # Change these credentials
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Ongeldige inloggegevens', 'error')
    
    return render_template('nindex.html', show_admin_login=True)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    quotes = list(quotes_collection.find().sort('created_at', -1))
    return render_template('nindex.html', show_admin_dashboard=True, quotes=quotes)

@app.route('/admin/quote/<quote_id>')
@login_required
def admin_quote_detail(quote_id):
    quote = quotes_collection.find_one({'quote_id': quote_id})
    if not quote:
        flash('Offerte niet gevonden', 'error')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('nindex.html', show_admin_quote_detail=True, quote=quote)

@app.route('/admin/update-status/<quote_id>', methods=['POST'])
@login_required
def update_quote_status(quote_id):
    new_status = request.form.get('status')
    quotes_collection.update_one(
        {'quote_id': quote_id},
        {'$set': {
            'status': new_status,
            'updated_at': datetime.now()
        }}
    )
    flash('Status succesvol bijgewerkt', 'success')
    return redirect(url_for('admin_quote_detail', quote_id=quote_id))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    app.run(debug=True)