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
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
import unicodedata

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
# VISTA 3: Consejos
# -----------------------------------------------------------------
@login_required
def vista_consejos(request):
    """Muestra la página de consejos."""
    return render(request, 'agendamiento/consejos.html')

# -----------------------------------------------------------------
# VISTA 4: Resultados (Gráficos)
# -----------------------------------------------------------------
@login_required
def vista_resultados(request):
    """
    Muestra la página de gráficos. La página se encargará
    de cargar sus propios datos usando JavaScript.
    """
    # Ya no pasamos ningún dato, solo renderizamos la plantilla.
    return render(request, 'agendamiento/resultados.html')

# -----------------------------------------------------------------
# VISTA 5: Registro de Usuario
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