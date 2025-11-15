from django.db import models

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

class BloqueHorario(models.Model):
    """
    Representa un bloque de agendamiento (ej. "Bloque 1-2").
    Estos son fijos y se crean una sola vez.
    """
    nombre = models.CharField(max_length=50, unique=True, help_text="Ej: Bloque 1-2")
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    capacidad_maxima = models.PositiveIntegerField(default=10)

    def __str__(self):
        return f"{self.nombre} ({self.hora_inicio.strftime('%H:%M')} - {self.hora_fin.strftime('%H:%M')})"

    class Meta:
        verbose_name = "Bloque Horario"
        verbose_name_plural = "Bloques Horarios"
        ordering = ['hora_inicio']

class Reserva(models.Model):
    """
    Conecta a un Usuario con un BloqueHorario en una fecha específica.
    """
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reservas")
    bloque = models.ForeignKey(BloqueHorario, on_delete=models.CASCADE, related_name="reservas")
    fecha = models.DateField(default=timezone.now)

    def __str__(self):
        return f"Reserva de {self.usuario.username} para {self.bloque.nombre} el {self.fecha}"

    class Meta:
        # Un usuario no puede reservar el mismo bloque el mismo día dos veces
        unique_together = ('usuario', 'bloque', 'fecha')
        verbose_name = "Reserva"
        verbose_name_plural = "Reservas"

    def clean(self):
        """
        Validación a nivel de modelo para asegurar que no se supere la capacidad.
        """
        # Contamos cuántas reservas existen ya para este bloque en esta fecha
        reservas_existentes = Reserva.objects.filter(
            bloque=self.bloque,
            fecha=self.fecha
        ).count()
        
        # Si las reservas existentes son iguales o mayores a la capacidad, lanzamos un error
        if reservas_existentes >= self.bloque.capacidad_maxima:
            raise ValidationError(
                f"El bloque {self.bloque.nombre} para el {self.fecha} está lleno."
            )

    def save(self, *args, **kwargs):
        # Ejecutar la validación 'clean' antes de guardar
        self.clean()
        super().save(*args, **kwargs)

class Sugerencia(models.Model):
    # Usamos ForeignKey para saber QUÉ usuario envió la sugerencia
    # "on_delete=models.SET_NULL" significa que si se borra el usuario,
    # la sugerencia no se borra, solo queda como "Anónimo".
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Usamos TextField para textos largos
    texto = models.TextField()
    
    # "auto_now_add=True" guarda automáticamente la fecha y hora de creación
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Esto es para que se vea bonito en el panel de administrador
        user_display = self.usuario.username if self.usuario else 'Anónimo'
        return f'Sugerencia de {user_display} ({self.fecha_creacion.strftime("%Y-%m-%d")})'
