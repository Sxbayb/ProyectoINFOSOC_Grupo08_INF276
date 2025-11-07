from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import BloqueHorario, Reserva
from django.contrib import messages
from django.utils import timezone
import datetime
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.conf import settings # Para rutas estáticas
import pandas as pd # Necesita `pip install pandas`
import requests     # Necesita `pip install requests`
import json
import io
import os
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login

# -----------------------------------------------------------------
# VISTA 1: Página Principal (NUEVA)
# -----------------------------------------------------------------
@login_required
def vista_principal(request):
    """Muestra el menú principal después del login."""
    return render(request, 'agendamiento/principal.html')

# -----------------------------------------------------------------
# VISTA 2: Agendamiento (ACTUALIZADA)
# -----------------------------------------------------------------
@login_required
def vista_agendamiento(request):
    
# --- Lógica para procesar una reserva (POST) ---
    if request.method == "POST":
        try:
            bloque_id = request.POST.get("bloque_id")
            fecha_str = request.POST.get("fecha")
            
            bloque = BloqueHorario.objects.get(id=bloque_id)
            fecha = datetime.datetime.strptime(fecha_str, "%Y-%m-%d").date()
            usuario = request.user

            # --- INICIO DE LA NUEVA VALIDACIÓN DE TIEMPO ---
            
            # 1. Combinamos la fecha seleccionada con la hora de inicio del bloque
            hora_inicio_reserva = datetime.datetime.combine(fecha, bloque.hora_inicio)
            
            # 2. Hacemos esa hora "consciente" de la zona horaria (usamos la zona horaria de tus settings)
            try:
                # Intenta obtener la zona horaria actual de Django
                current_tz = timezone.get_current_timezone()
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, current_tz)
            except Exception:
                # Fallback por si la zona horaria no está bien configurada (usa UTC)
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, timezone.utc)

            # 3. Obtenemos el momento actual, también consciente de la zona horaria
            ahora = timezone.now()

            # 4. Comparamos
            if hora_inicio_reserva_tz < ahora:
                messages.error(request, "Error: No puedes reservar un bloque de horario que ya ha pasado.")
                return redirect('vista_agendamiento')
            
            # --- FIN DE LA NUEVA VALIDACIÓN DE TIEMPO ---

            # 1. (Validación anterior) Verificar si el usuario ya tiene una reserva
            reserva_existente = Reserva.objects.filter(usuario=usuario, bloque=bloque, fecha=fecha).exists()
            if reserva_existente:
                messages.error(request, f"Ya tienes una reserva para el {bloque.nombre} el {fecha}.")
                return redirect('vista_agendamiento')

            # 2. (Validación anterior) La validación de capacidad se hace en el models.py (clean/save)
            Reserva.objects.create(
                usuario=usuario,
                bloque=bloque,
                fecha=fecha
            )
            messages.success(request, f"¡Reserva confirmada! {bloque.nombre} el {fecha}.")
            return redirect('vista_agendamiento')

        except ValidationError as e: 
            error_message = ". ".join(e.messages)
            messages.error(request, f"Error al reservar: {error_message}")
            return redirect('vista_agendamiento')
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")
            return redirect('vista_agendamiento')

    # --- Lógica para mostrar la página (GET) ---
    hoy = timezone.localdate()
    ahora = timezone.now()
    lunes_de_esta_semana = hoy - datetime.timedelta(days=hoy.weekday())
    dias_de_la_semana = [lunes_de_esta_semana + datetime.timedelta(days=i) for i in range(5)]
    bloques_horarios = BloqueHorario.objects.all().order_by('hora_inicio')

    reservas_usuario = Reserva.objects.filter(
        usuario=request.user,
        fecha__in=dias_de_la_semana
    ).values_list('bloque_id', 'fecha')
    
    set_reservas_usuario = set((r[0], r[1]) for r in reservas_usuario)

    todas_las_reservas = Reserva.objects.filter(
        fecha__in=dias_de_la_semana
    ).values('bloque', 'fecha').annotate(conteo=Count('id'))

    conteo_reservas = {
        (reserva['bloque'], reserva['fecha']): reserva['conteo']
        for reserva in todas_las_reservas
    }

    datos_para_plantilla = []
    
    for bloque in bloques_horarios:
        datos_de_la_fila = []
        for dia in dias_de_la_semana:
            reservas_count = conteo_reservas.get((bloque.id, dia), 0)
            cupos_disponibles = bloque.capacidad_maxima - reservas_count
            reservado_por_usuario = (bloque.id, dia) in set_reservas_usuario
            
            hora_inicio_reserva = datetime.datetime.combine(dia, bloque.hora_inicio)
            try:
                current_tz = timezone.get_current_timezone()
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, current_tz)
            except Exception:
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, timezone.utc)

            es_pasado = hora_inicio_reserva_tz < ahora

            datos_de_la_fila.append({
                'cupos': cupos_disponibles,
                'reservado': reservado_por_usuario,
                'fecha_str': dia.isoformat(),
                'es_pasado': es_pasado
            
            })
        datos_para_plantilla.append((bloque, datos_de_la_fila))

    context = {
        'dias_de_la_semana': dias_de_la_semana,
        'datos_para_plantilla': datos_para_plantilla, 
    }
    
    return render(request, 'agendamiento/agendar.html', context)

# -----------------------------------------------------------------
# VISTA 3: Consejos (NUEVA)
# -----------------------------------------------------------------
@login_required
def vista_consejos(request):
    """Muestra la página de consejos."""
    return render(request, 'agendamiento/consejos.html')


# -----------------------------------------------------------------
# VISTA 4: Resultados (Gráficos) (NUEVA Y COMPLEJA)
# -----------------------------------------------------------------
def normalize_string(s):
    """Normaliza strings para comparar cabeceras de CSV."""
    if not isinstance(s, str):
        return ""

    # Eliminamos s.normalize("NFD") que estaba causando el error
    # y las líneas encode/decode que eran redundantes.
    return s.replace("¿", "").replace("?", "").replace("(", "").replace(")", "").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").lower().strip()
    
def get_survey_data():
    """Función para procesar los datos de la encuesta en Python."""
    
    # --- 1. Definir rutas a los archivos ---
    static_dir = settings.STATICFILES_DIRS[0]
    local_csv_path = os.path.join(static_dir, 'data', 'encuesta_resultados_limpios.csv')
    structure_json_path = os.path.join(static_dir, 'data', 'encuesta_from_excel.json')
# ESTAS LÍNEAS ESTÁN CORREGIDAS
    google_sheet_url = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vSwQAawOukFYJfpuQnx5_BhpR1R1QbtaEhf167hrGWImQ-BFfkAocf_QGuMcHKoFV3ObWiDxyHhtwGU/pub?output=csv'
    google_form_url = 'https://docs.google.com/forms/d/e/1FAIpQLSc5XkDHOuZf2JHeJ1kYzNDe-pTEb-WYrSGoLaPWQ71otL_uqA/viewform?usp=header'
    # --- 2. Cargar datos base ---
    try:
        local_data = pd.read_csv(local_csv_path)
    except Exception as e:
        print(f"Error cargando CSV local: {e}")
        local_data = pd.DataFrame(columns=['section', 'question', 'option', 'count'])

    try:
        with open(structure_json_path, 'r', encoding='utf-8') as f:
            survey_structure = json.load(f)
        questions_list = survey_structure.get('questions', [])
    except Exception as e:
        print(f"Error cargando JSON de estructura: {e}")
        questions_list = []

    # --- 3. Cargar datos de Google Sheet ---
    live_data_list = []
    try:
        r = requests.get(google_sheet_url)
        r.raise_for_status()
        live_csv_text = r.text
        
        # Leer el CSV en un DataFrame de pandas
        live_df = pd.read_csv(io.StringIO(live_csv_text))
        
        # Mapear cabeceras normalizadas a texto de pregunta
        header_map = {}
        for header in live_df.columns:
            norm_header = normalize_string(header)
            for q_info in questions_list:
                norm_question = normalize_string(q_info['text'])
                if norm_question in norm_header:
                    header_map[header] = (q_info['text'], q_info['section'])
                    break
        
        # Procesar los datos en vivo
        for _, row in live_df.iterrows():
            for header, (question_text, section) in header_map.items():
                answer = row.get(header)
                if pd.notna(answer):
                    # Normalizar respuestas "Si" y "Sí"
                    if normalize_string(str(answer)) == "si":
                        answer = "Si"
                    
                    live_data_list.append({
                        'section': section,
                        'question': question_text,
                        'option': str(answer),
                        'count': 1
                    })
    except Exception as e:
        print(f"Error cargando o procesando Google Sheet: {e}")

    live_data = pd.DataFrame(live_data_list)

    # --- 4. Combinar datos ---
    combined_df = pd.concat([local_data, live_data])
    
    # Agrupar y sumar
    if not combined_df.empty:
        final_counts = combined_df.groupby(['section', 'question', 'option'])['count'].sum().reset_index()
    else:
        final_counts = combined_df

    # --- 5. Formatear para los gráficos ---
    chart_data = {
        'Problemas': [],
        'Alimentacion': [],
        'Salud Fisica': []
    }
    total_responses = 0

    # Usar la estructura del JSON para mantener el orden
    if questions_list: # Solo si el JSON cargó bien
        first_question_text = questions_list[0]['text']
        for q_info in questions_list:
            question_text = q_info['text']
            section = q_info['section']
            
            # Filtrar datos para esta pregunta
            q_data = final_counts[final_counts['question'] == question_text]
            
            if not q_data.empty:
                labels = q_data['option'].tolist()
                data = q_data['count'].tolist()
                
                # Calcular total (solo para la primera pregunta)
                if question_text == first_question_text:
                    total_responses = sum(data)
                
                chart_data[section].append({
                    'title': question_text,
                    'labels': labels,
                    'data': data
                })
    else: # Fallback si el JSON no carga
        if not final_counts.empty:
             total_responses = final_counts[final_counts['question'] == final_counts['question'].iloc[0]]['count'].sum()


    return chart_data, total_responses, google_form_url

@login_required
def vista_resultados(request):
    """Muestra la página de gráficos, procesando los datos en Python."""
    try:
        chart_data, total_responses, gform_url = get_survey_data()
        context = {
            'chart_data_json': json.dumps(chart_data), # Convertimos a JSON para pasarlo a JS
            'total_responses': total_responses,
            'gform_url': gform_url
        }
        return render(request, 'agendamiento/resultados.html', context)
    except Exception as e:
        messages.error(request, f"Error al generar los gráficos: {e}")
        return render(request, 'agendamiento/resultados.html', {'error': str(e)})

# -----------------------------------------------------------------
# VISTA 6: Registro de Usuario (NUEVA)
# -----------------------------------------------------------------
def vista_registro(request):
    """Muestra y procesa un formulario de registro de nuevos usuarios."""
    
    if request.method == 'POST':
        # Si el formulario se envió (POST)
        form = UserCreationForm(request.POST)
        
        if form.is_valid():
            # El formulario es válido (contraseñas coinciden, username no existe)
            user = form.save()  # Guarda el nuevo usuario en la base de datos
            
            # Opcional, pero recomendado: Iniciar sesión automáticamente
            login(request, user)
            
            messages.success(request, '¡Te has registrado con éxito! Ya puedes agendar tu hora.')
            return redirect('vista_principal') # Redirige al portal principal
        else:
            # Si el formulario no es válido, los errores se mostrarán
            messages.error(request, 'Hubo un error en el registro. Por favor, revisa los campos.')
            
    else:
        # Si es la primera vez que se carga la página (GET)
        form = UserCreationForm()
        
    # Muestra la plantilla 'registro.html' con el formulario
    return render(request, 'agendamiento/registro.html', {'form': form})