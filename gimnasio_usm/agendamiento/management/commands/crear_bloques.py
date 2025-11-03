import datetime
from django.core.management.base import BaseCommand
from agendamiento.models import BloqueHorario

class Command(BaseCommand):
    help = 'Crea los 10 bloques horarios del gimnasio con sus reglas de recreos y almuerzo.'

    def handle(self, *args, **options):
        self.stdout.write("Eliminando bloques horarios antiguos...")
        BloqueHorario.objects.all().delete()

        self.stdout.write("Creando nuevos bloques horarios...")
        
        # 10 bloques dobles (20 bloques en total)
        total_bloques_dobles = 10
        duracion_bloque_doble = datetime.timedelta(minutes=70) # 35 min * 2
        duracion_recreo = datetime.timedelta(minutes=15)
        hora_almuerzo = datetime.timedelta(hours=1)
        
        # Empezamos a las 8:15 AM
        hora_actual = datetime.time(8, 15)
        
        # Usamos una fecha ficticia para poder sumar timedeltas
        fecha_ficticia = datetime.date.today()

        for i in range(total_bloques_dobles):
            # Calculamos inicio y fin
            inicio_dt = datetime.datetime.combine(fecha_ficticia, hora_actual)
            fin_dt = inicio_dt + duracion_bloque_doble
            
            nombre_bloque = f"Bloque {i*2 + 1}-{i*2 + 2}"

            # Creamos el bloque en la BD
            bloque = BloqueHorario.objects.create(
                nombre=nombre_bloque,
                hora_inicio=inicio_dt.time(),
                hora_fin=fin_dt.time()
            )
            self.stdout.write(self.style.SUCCESS(f"Creado: {bloque}"))

            # Actualizamos la hora_actual para el siguiente bloque
            
            # Caso especial: Bloque 7-8 (índice 3)
            # i=0 (Bloque 1-2)
            # i=1 (Bloque 3-4)
            # i=2 (Bloque 5-6)
            # i=3 (Bloque 7-8) -> Este es el bloque antes del almuerzo
            if i == 3:
                self.stdout.write(self.style.NOTICE("-> Recreo de Almuerzo (1 hora)"))
                siguiente_inicio_dt = fin_dt + hora_almuerzo
            else:
                siguiente_inicio_dt = fin_dt + duracion_recreo
            
            hora_actual = siguiente_inicio_dt.time()

        self.stdout.write(self.style.SUCCESS("¡Todos los bloques han sido creados!"))
