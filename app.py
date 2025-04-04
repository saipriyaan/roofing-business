import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import uuid
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from io import BytesIO
from functools import wraps

app = Flask(__name__)
app.secret_key = 'dakwerken_secret_key_2025'

# MongoDB Configuration
client = MongoClient('mongodb+srv://sai:8778386853@cluster0.9vhjs.mongodb.net/quotbusiness?retryWrites=true&w=majority&appName=Cluster0')
db = client['quote_calculator']
quotes_collection = db['quotes']
users_collection = db['users']
MAIL_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
MAIL_USERNAME='serviceemailshop@gmail.com'
MAIL_PASSWORD='ukdqyqjvqepfeuad'
ADMIN_EMAIL='expenditure.cob@gmail.com'

# Pricing Data
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
        'voorrijden_30_60': {'price': 45.0, 'label': 'Voorrijkosten (30-60 km)'},
        'voorrijden_60_plus': {'price': 75.0, 'label': 'Voorrijkosten (meer dan 60 km)'},
    },
    'Staffelkorting': {
        'korting_50m2': {'price': -0.05, 'label': 'Staffelkorting vanaf 50 m²'},
        'korting_100m2': {'price': -0.1, 'label': 'Staffelkorting vanaf 100 m²'},
    }
}
FORM_FLOW = [
    # Step 1: Introduction/General Information
    {
        'step': 1,
        'question': 'Wat voor werk wilt u laten uitvoeren?',
        'type': 'single',
        'options': ['Nieuw dak', 'Dakrenovatie', 'Reparatie', 'Isolatie', 'Inspectie'],
        'next_step': 2,
        'logic': {'Reparatie': 7}  # Skip to damage step if "Reparatie"
    },
    # Step 2: Roof Type
    {
      'step': 2,
        'question': 'Wat voor dak heeft u?',
        'type': 'single',
        'options': ['Plat dak', 'Hellend dak', 'Beide', 'Weet ik niet'],
        'next_step': 3  # Always proceed to Step 3
    },
    # Step 3: Current Roof Material (Dynamic filtering)
    {
        'step': 3,
        'question': 'Wat is de huidige dakbedekking?',
        'type': 'single',
        'options': [],  # Placeholder (set dynamically)
        'next_step': 4,
        'logic': {
            # Options for flat roofs
            'Plat dak': {
                'options': ['Bitumen', 'EPDM', 'PVC', 'Weet ik niet'],
                'next_step': 4
            },
            # Options for slanted roofs
            'Hellend dak': {
                'options': ['Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Weet ik niet'],
                'next_step': 4
            },
            # Combined options for "Both"
            'Beide': {
                'options': ['Bitumen', 'EPDM', 'PVC', 'Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Weet ik niet'],
                'next_step': 4
            },
            # Default fallback
            'Weet ik niet': {
                'options': ['Bitumen', 'EPDM', 'PVC', 'Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Weet ik niet'],
                'next_step': 4
            }
        }
    },
    # Step 4: Desired New Roof Material
    {
        'step': 4,
        'question': 'Wat is de gewenste nieuwe dakbedekking?',
        'type': 'single',
        'options': ['Bitumen', 'EPDM', 'PVC', 'Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Geen voorkeur'],
        'next_step': 5  # Proceed to square meters
    },
    # Step 5: Square Footage
    {
        'step': 5,
        'question': 'Hoeveel m² betreft het?',
        'type': 'input',
        'next_step': 6,
        'logic': {'empty': {'show_upload': True}}  # Allow upload if no input
    },
    # Step 6: Roof Condition
    {
        'step': 6,
        'question': 'Wat is de staat van het huidige dak?',
        'type': 'single',
        'options': ['Goed', 'Verouderd', 'Slecht of beschadigd', 'Nieuwbouw'],
        'next_step': 8,
        'logic': {'Slecht of beschadigd': 7}  # Skip to damage step
    },
    # Step 7: Damage Type
    {
        'step': 7,
        'question': 'Wat is de aard van de schade?',
        'type': 'single',
        'options': ['Lekkage', 'Losse dakbedekking', 'Constructieproblemen', 'Anders'],
        'next_step': 8  # Proceed to material removal
    },
    # Step 8: Material Removal
    {
        'step': 8,
        'question': 'Moet de huidige dakbedekking verwijderd worden?',
        'type': 'single',
        'options': ['Ja', 'Nee', 'Weet ik niet'],
        'next_step': 9  # Proceed to extra elements
    },
    # Step 9: Additional Elements
    {
        'step': 9,
        'question': 'Zijn er extra elementen aanwezig op het dak?',
        'type': 'multi',
        'options': ['Dakkapel', 'Dakraam', 'Schoorsteen', 'Ventilatiepijp', 'Zonnepanelen', 'Geen'],
        'next_step': 10  # Proceed to insulation
    },
    # Step 10: Insulation
    {
        'step': 10,
        'question': 'Wat is de huidige isolatie?',
        'type': 'single',
        'options': ['Geen', 'Binnenzijde', 'Buitenzijde', 'Weet ik niet'],
        'next_step': 11  # Proceed to address
    },
    # Step 11: Address and Contact Info
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
    # Step 13: Upload Photos/Documents (Optional)
    {
        'step': 13,
        'question': 'Upload foto\'s of documenten',
        'type': 'upload',
        'next_step': 14
    },
    # Step 14: Cost Calculation (Dynamic)
    {
        'step': 14,
        'question': 'Richtprijsberekening  please press next',
        'type': 'calculation',  # Custom logic for costs/discounts
        'logic': {
            'staffelkorting': [
                {'threshold': 50, 'discount': '5%'},
                {'threshold': 100, 'discount': '10%'}
            ],
            'travel_costs': True  # Calculate based on address
        },
        'next_step': 15
    },
    # Step 15: Final Options
    {
        'step': 15,
        'question': 'Hoe wilt u de richtprijs ontvangen?',
        'type': 'single',
        'options': ['Toon op scherm', 'Mail mij de richtprijs', 'Alleen contact opnemen'],
        'next_step': None  # End of flow
    }
]
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def generate_dutch_pdf(quote_data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4, 
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm
    )
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DutchTitle', 
                            fontSize=16, 
                            leading=18,
                            alignment=1,
                            fontName='Helvetica-Bold'))
    
    styles.add(ParagraphStyle(name='DutchHeader',
                            fontSize=12,
                            leading=14,
                            fontName='Helvetica-Bold'))
    
    styles.add(ParagraphStyle(name='DutchText',
                            fontSize=10,
                            leading=12))
    
    # helper to convert table cell content to Paragraph if it is a string
    def to_paragraph(cell):
        if isinstance(cell, str):
            return Paragraph(cell, styles['DutchText'])
        return cell
    
    elements = []
    
    # Header
    elements.append(Paragraph("OFFERTE", styles['DutchTitle']))
    elements.append(Spacer(1, 10*mm))
    
    # Company and client info
    company_info = [
        ["Bedrijfsgegevens:", ""],
        ["Dakwerken BV", ""],
        ["Industrieweg 100", ""],
        ["1234 AB Amsterdam", ""],
        ["Tel: 020-1234567", ""],
        ["Email: info@dakwerkenbv.nl", ""],
        ["KVK: 12345678", ""],
        ["BTW: NL123456789B01", ""]
    ]
    client_info = [
        ["Klantgegevens:", ""],
        ["Naam:", quote_data['form_data'].get('Naam', '')],
        ["Adres:", quote_data['form_data'].get('Adres_van_de_woning', '')],
        ["Telefoon:", quote_data['form_data'].get('Telefoonnummer', '')],
        ["Email:", quote_data['form_data'].get('E-mailadres', '')]
    ]
    
    # Convert cell texts to Paragraphs
    company_info = [[to_paragraph(cell) for cell in row] for row in company_info]
    client_info = [[to_paragraph(cell) for cell in row] for row in client_info]
    
    info_table = Table([[company_info, client_info]], colWidths=[90*mm, 90*mm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 10*mm))
    
    # Quote details
    elements.append(Paragraph(f"Offertenummer: {quote_data['quote_id']}", styles['DutchHeader']))
    elements.append(Paragraph(f"Datum: {datetime.now().strftime('%d-%m-%Y')}", styles['DutchHeader']))
    elements.append(Spacer(1, 10*mm))
    
    # Items table
    data = [["Omschrijving", "Aantal", "Prijs", "Totaal"]]
    
    for item in quote_data['quote_details']['items']:
        data.append([
            to_paragraph(item['description']),
            to_paragraph(str(item['quantity'])),
            to_paragraph(f"€ {item['unit_price']:,.2f}".replace(".", ",")),
            to_paragraph(f"€ {item['total']:,.2f}".replace(".", ","))
        ])
    
    # Add totals
    data.append([
        "", "", 
        to_paragraph("Subtotaal:"), 
        to_paragraph(f"€ {quote_data['quote_details']['subtotal']:,.2f}".replace(".", ","))
    ])
    data.append([
        "", "", 
        to_paragraph("BTW (21%):"), 
        to_paragraph(f"€ {quote_data['quote_details']['tax']:,.2f}".replace(".", ","))
    ])
    data.append([
        "", "", 
        to_paragraph("Totaal:"), 
        to_paragraph(f"€ {quote_data['quote_details']['total']:,.2f}".replace(".", ","))
    ])
    
    items_table = Table(data, colWidths=[90*mm, 20*mm, 30*mm, 30*mm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F2F2F2")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('ALIGN', (0,0), (0,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-4), 0.5, colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (-2,-3), (-1,-1), 'Helvetica-Bold'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 15*mm))
    
    # Terms and conditions
    elements.append(Paragraph("Voorwaarden:", styles['DutchHeader']))
    terms = [
        "1. Deze offerte is 30 dagen geldig vanaf de datum van uitgifte",
        "2. Alle prijzen zijn inclusief BTW",
        "3. Betaling binnen 14 dagen na factuurdatum",
        "4. Wijzigingen moeten schriftelijk worden bevestigd",
        "5. Onvoorziene werkzaamheden worden apart gefactureerd"
    ]
    for term in terms:
        elements.append(Paragraph(term, styles['DutchText']))
        elements.append(Spacer(1, 3*mm))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

def calculate_quote(form_data):
    total = 0
    items = []
    
    # Get basic information
    werk_type = form_data.get('wat_voor_werk_wilt_u_laten_uitvoeren?', [])
    if isinstance(werk_type, str):
        werk_type = [werk_type]
    
    dak_type = form_data.get('wat_voor_dak_heeft_u?', '')
    oppervlakte = float(form_data.get('hoeveel_m²_betreft_het?', 0))
    
    # Calculate roof covering
    if 'Nieuw dak' in werk_type or 'Dakrenovatie' in werk_type:
        gewenste_dakbedekking = form_data.get('wat_is_de_gewenste_nieuwe_dakbedekking?', '')
        
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
    
    # Calculate removal if needed
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
        
        if 'item' in locals():
            cost = item['price'] * oppervlakte
            items.append({
                'description': item['label'],
                'quantity': oppervlakte,
                'unit_price': item['price'],
                'total': cost
            })
            total += cost
    
    # Calculate insulation
    isolatie = form_data.get('wat_is_de_huidige_isolatie?', '')
    if isolatie == 'Binnenzijde':
        item = PRICES['Isolatie']['isolatie_binnen']
    elif isolatie == 'Buitenzijde':
        item = PRICES['Isolatie']['isolatie_buiten']
    
    if 'item' in locals():
        cost = item['price'] * oppervlakte
        items.append({
            'description': item['label'],
            'quantity': oppervlakte,
            'unit_price': item['price'],
            'total': cost
        })
        total += cost
    
    # Calculate repairs
    if 'Reparatie' in werk_type:
        schade = form_data.get('wat_is_de_aard_van_de_schade?', '')
        if schade == 'Lekkage':
            item = PRICES['Reparatie']['reparatie_klein']
        elif schade in ['Losse dakbedekking', 'Constructieproblemen', 'Anders']:
            item = PRICES['Reparatie']['reparatie_groot']
        
        if 'item' in locals():
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
        
        if 'item' in locals():
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
        total += discount_amount
    
    # Add travel costs
    items.append({
        'description': 'Voorrijkosten',
        'quantity': 1,
        'unit_price': 0,
        'total': 0
    })
    
    # Calculate tax and totals
    tax = total * 0.21
    grand_total = total + tax
    
    return {
        'items': items,
        'subtotal': total,
        'tax': tax,
        'total': grand_total
    }

def send_admin_notification(quote_data):
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_USERNAME
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
        {request.url_root}admin/quote/{quote_data['quote_id']}
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(MAIL_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
        
        print("Admin notification sent successfully")
    except Exception as e:
        print(f"Error sending admin notification: {str(e)}")

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
        Totaalbedrag: €{quote_data["quote_details"]["total"]:,.2f}
        
        U kunt de offerte downloaden via onderstaande link:
        {request.url_root}download-quote/{quote_data['quote_id']}
        
        Met vriendelijke groet,
        Dakwerken BV
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach PDF
        pdf_buffer = generate_dutch_pdf(quote_data)
        pdf_attachment = MIMEApplication(pdf_buffer.read(), _subtype="pdf")
        pdf_attachment.add_header('Content-Disposition', 'attachment', filename=f"Offerte_{quote_data['quote_id']}.pdf")
        msg.attach(pdf_attachment)
        
        with smtplib.SMTP(MAIL_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
        
        print("Quote email sent successfully to client")
    except Exception as e:
        print(f"Error sending quote to client: {str(e)}")

@app.route('/')
def index():
    if 'current_step' not in session:
        session['current_step'] = 1
        session['form_data'] = {}
        session['quote_id'] = str(uuid.uuid4())
    
    # Check for resume functionality
    if 'email' in request.args:
        user_data = users_collection.find_one({'email': request.args.get('email')})
        if user_data:
            session['current_step'] = user_data['current_step']
            session['form_data'] = user_data['form_data']
            session['quote_id'] = user_data['quote_id']
            return redirect(url_for('form_step', step=session['current_step']))
    
    return redirect(url_for('form_step', step=session['current_step']))

@app.route('/form/step/<int:step>', methods=['GET', 'POST'])
def form_step(step):
    if request.method == 'POST':
        current_question = FORM_FLOW[step-1]
        field_name = current_question.get('question', '').replace(' ', '_').lower()
        
        # Handle different question types
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
                    
                    session['form_data']['uploaded_files'] = session['form_data'].get('uploaded_files', [])
                    session['form_data']['uploaded_files'].append({
                        'name': filename,
                        'path': upload_path
                    })
        else:
            session['form_data'][field_name] = request.form.get(field_name, '')
        
        # Save progress
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
        
        # Determine next step
        next_step = current_question['next_step']
        
        # Check conditional logic
        if 'logic' in current_question:
            answer = request.form.get(field_name, '')
            if answer in current_question['logic']:
                logic_result = current_question['logic'][answer]
                if isinstance(logic_result, dict):
                    next_step = logic_result.get('next_step', next_step)
                else:
                    next_step = logic_result
        
        if next_step:
            session['current_step'] = next_step
            return redirect(url_for('form_step', step=next_step))
        else:
            return redirect(url_for('generate_quote'))
    
    # GET request handling
    if step < 1 or step > len(FORM_FLOW):
        return redirect(url_for('index'))
    
    current_question = FORM_FLOW[step-1].copy()
    if step == 3:
        dak_type = session.get('form_data', {}).get('wat_voor_dak_heeft_u?', '')
        
        if dak_type == 'Plat dak':
            current_question['options'] = ['Bitumen', 'EPDM', 'PVC', 'Weet ik niet']
        elif dak_type == 'Hellend dak':
            current_question['options'] = ['Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Weet ik niet']
        elif dak_type in ['Beide', 'Weet ik niet']:
            current_question['options'] = [
                'Bitumen', 'EPDM', 'PVC', 'Dakpannen', 
                'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Weet ik niet'
            ]
    # Apply filtering logic for options
    if step == 4:  # New roof covering question
        dak_type = session.get('form_data', {}).get('wat_voor_dak_heeft_u?', '')
        if dak_type == 'Plat dak' and 'logic' in FORM_FLOW[1] and 'Plat dak' in FORM_FLOW[1]['logic']:
            current_question['options'] = [
                opt for opt in current_question['options'] 
                if opt in ['Bitumen', 'EPDM', 'PVC', 'Geen voorkeur']
            ]
        elif dak_type == 'Hellend dak' and 'logic' in FORM_FLOW[1] and 'Hellend dak' in FORM_FLOW[1]['logic']:
            current_question['options'] = [
                opt for opt in current_question['options'] 
                if opt in ['Dakpannen', 'Leien (kunststof)', 'Leien (natuursteen)', 'Zink', 'Geen voorkeur']
            ]
    
    return render_template('nindex.html', 
                         question=current_question, 
                         step=step, 
                         total_steps=len(FORM_FLOW),
                         form_data=session.get('form_data', {}))

@app.route('/generate-quote')
def generate_quote():
    if 'form_data' not in session:
        return redirect(url_for('index'))
    
    form_data = session['form_data']
    quote = calculate_quote(form_data)
    
    # Save complete quote
    quote_data = {
        'quote_id': session['quote_id'],
        'user_email': session.get('email', ''),
        'form_data': form_data,
        'quote_details': quote,
        'status': 'pending',
        'created_at': datetime.now(),
        'updated_at': datetime.now()
    }
    quotes_collection.insert_one(quote_data)
    
    # Send notifications
    send_admin_notification(quote_data)
    send_quote_to_client(quote_data)
    
    ontvangst_voorkeur = form_data.get('wilt_u_direct_een_richtprijs_ontvangen?', '')
    if ontvangst_voorkeur == 'Mail mij de richtprijs':
        send_quote_to_client(quote_data)
        flash('Uw offerte is naar uw e-mailadres verzonden!', 'success')
    elif ontvangst_voorkeur == 'Alleen contact opnemen':
        flash('Wij nemen zo snel mogelijk contact met u op!', 'success')
    
    return render_template('nindex.html',
                         show_quote=True,
                         quote=quote,
                         form_data=form_data,
                         quote_id=session['quote_id'],
                         ontvangst_voorkeur=ontvangst_voorkeur)

@app.route('/download-quote/<quote_id>')
def download_quote(quote_id):
    quote = quotes_collection.find_one({'quote_id': quote_id})
    if not quote:
        flash('Offerte niet gevonden', 'error')
        return redirect(url_for('index'))
    
    pdf_buffer = generate_dutch_pdf(quote)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"Offerte_{quote_id}.pdf",
        mimetype='application/pdf'
    )

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # In production, use proper password hashing!
        if username == 'admin' and password == 'dakwerken2025':
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
    os.makedirs('static', exist_ok=True)
    app.run(debug=True)