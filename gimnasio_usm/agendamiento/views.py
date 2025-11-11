from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import BloqueHorario, Reserva
from django.contrib import messages
from django.utils import timezone
import datetime
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.conf import settings # Para rutas estáticas
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

# -----------------------------------------------------------------
# VISTA 1: Página Principal (NUEVA)
# -----------------------------------------------------------------
@login_required
def vista_principal(request):
    """Muestra el menú principal después del login."""
    return render(request, 'agendamiento/principal.html')

# -----------------------------------------------------------------
# VISTA 2: Agendamiento (ACTUALIZADA para Cancelar)
# -----------------------------------------------------------------
@login_required
def vista_agendamiento(request):
    
    if request.method == "POST":
        try:
            bloque_id = request.POST.get("bloque_id")
            fecha_str = request.POST.get("fecha")
            bloque = BloqueHorario.objects.get(id=bloque_id)
            fecha = datetime.datetime.strptime(fecha_str, "%Y-%m-%d").date()
            usuario = request.user

            # Validación de tiempo
            hora_inicio_reserva = datetime.datetime.combine(fecha, bloque.hora_inicio)
            try:
                current_tz = timezone.get_current_timezone()
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, current_tz)
            except Exception:
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, timezone.utc)
            
            if hora_inicio_reserva_tz < timezone.now():
                messages.error(request, "Error: No puedes reservar un bloque de horario que ya ha pasado.")
                return redirect('vista_agendamiento')

            reserva_existente = Reserva.objects.filter(usuario=usuario, bloque=bloque, fecha=fecha).exists()
            if reserva_existente:
                messages.error(request, f"Ya tienes una reserva para el {bloque.nombre} el {fecha}.")
                return redirect('vista_agendamiento')

            Reserva.objects.create(usuario=usuario, bloque=bloque, fecha=fecha)
            messages.success(request, f"¡Reserva confirmada! {bloque.nombre} el {fecha}.")
            return redirect('vista_agendamiento')

        except ValidationError as e: 
            messages.error(request, f"Error al reservar: {'. '.join(e.messages)}")
            return redirect('vista_agendamiento')
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")
            return redirect('vista_agendamiento')

    # GET: Mostrar Horario
    hoy = timezone.localdate()
    ahora = timezone.now()
    lunes_de_esta_semana = hoy - datetime.timedelta(days=hoy.weekday())
    dias_de_la_semana = [lunes_de_esta_semana + datetime.timedelta(days=i) for i in range(5)]
    bloques_horarios = BloqueHorario.objects.all().order_by('hora_inicio')

    # --- CAMBIO CLAVE: Obtenemos el objeto reserva completo, no solo IDs ---
    reservas_usuario_qs = Reserva.objects.filter(
        usuario=request.user,
        fecha__in=dias_de_la_semana
    )
    # Mapa para encontrar rápido el ID de reserva: {(bloque_id, fecha): reserva_id}
    mapa_reservas_usuario = {(r.bloque_id, r.fecha): r.id for r in reservas_usuario_qs}
    # ---------------------------------------------------------------------

    todas_las_reservas = Reserva.objects.filter(fecha__in=dias_de_la_semana).values('bloque', 'fecha').annotate(conteo=Count('id'))
    conteo_reservas = {(reserva['bloque'], reserva['fecha']): reserva['conteo'] for reserva in todas_las_reservas}

    datos_para_plantilla = []
    for bloque in bloques_horarios:
        datos_de_la_fila = []
        for dia in dias_de_la_semana:
            reservas_count = conteo_reservas.get((bloque.id, dia), 0)
            cupos_disponibles = bloque.capacidad_maxima - reservas_count
            
            # Buscamos si el usuario tiene reserva aquí
            reserva_id = mapa_reservas_usuario.get((bloque.id, dia))
            
            hora_inicio_reserva = datetime.datetime.combine(dia, bloque.hora_inicio)
            try:
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, timezone.get_current_timezone())
            except:
                hora_inicio_reserva_tz = timezone.make_aware(hora_inicio_reserva, timezone.utc)

            es_pasado = hora_inicio_reserva_tz < ahora

            datos_de_la_fila.append({
                'cupos': cupos_disponibles,
                'reserva_id': reserva_id, # Pasamos el ID (o None)
                'fecha_str': dia.isoformat(),
                'es_pasado': es_pasado
            })
        datos_para_plantilla.append((bloque, datos_de_la_fila))

    return render(request, 'agendamiento/agendar.html', {
        'dias_de_la_semana': dias_de_la_semana,
        'datos_para_plantilla': datos_para_plantilla, 
    })
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

# -----------------------------------------------------------------
# VISTA 6: Cancelar Reserva
# -----------------------------------------------------------------

@login_required
@require_POST # Solo permite peticiones POST para mayor seguridad
def cancelar_reserva(request, reserva_id):
    """
    Permite a un usuario cancelar una de sus propias reservas.
    """
    # Buscamos la reserva. Si no existe o no pertenece al usuario actual, da error 404.
    reserva = get_object_or_404(Reserva, id=reserva_id, usuario=request.user)
    
    # Opcional: Validar que la reserva sea futura (para no cancelar reservas pasadas)
    # hoy = timezone.localdate()
    # if reserva.fecha < hoy:
    #     messages.error(request, "No puedes cancelar reservas de días pasados.")
    #     return redirect('vista_agendamiento')

    # Guardamos los datos para el mensaje de confirmación antes de borrar
    bloque_nombre = reserva.bloque.nombre
    fecha_reserva = reserva.fecha

    # Borramos la reserva
    reserva.delete()
    
    messages.success(request, f"Reserva para {bloque_nombre} el {fecha_reserva} cancelada exitosamente.")
    return redirect('vista_agendamiento')