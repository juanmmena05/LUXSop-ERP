from datetime import datetime
from zoneinfo import ZoneInfo
from .extensions import db

def now_cdmx():
    """Retorna datetime actual en hora de México (naive, sin tzinfo para BD)"""
    return datetime.now(ZoneInfo('America/Mexico_City')).replace(tzinfo=None)
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# ======================================================
# 1. ÁREAS Y SUBÁREAS
# ======================================================
class Area(db.Model):
    __tablename__ = 'area'

    area_id = db.Column(db.String(50), primary_key=True)
    area_nombre = db.Column(db.String(100))
    division = db.Column(db.String(50))
    grupo_fracciones = db.Column(db.String(20), nullable=True)
    cantidad_subareas = db.Column(db.Integer)
    orden_area = db.Column(db.Integer, nullable=True)
    subareas = db.relationship("SubArea", back_populates="area")


class SubArea(db.Model):
    __tablename__ = 'sub_area'

    subarea_id = db.Column(db.String, primary_key=True)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), nullable=False, index=True)

    subarea_nombre = db.Column(db.String, nullable=False)
    superficie_subarea = db.Column(db.Float)
    frecuencia = db.Column(db.Float)
    orden_subarea = db.Column(db.Integer, default=1000)

    area = db.relationship("Area", back_populates="subareas")

    sop = db.relationship(
        "SOP",
        back_populates="subarea",
        uselist=False,
        cascade="all, delete-orphan"
    )

    elementos = db.relationship(
        "Elemento",
        back_populates="subarea",
        cascade="all, delete-orphan"
    )

    elemento_sets = db.relationship(
        "ElementoSet",
        back_populates="subarea",
        cascade="all, delete-orphan"
    )


# ======================================================
# 2. SOP (STANDARD OPERATING PROCEDURE) 
# ======================================================
class SOP(db.Model):
    __tablename__ = 'sop'

    sop_id = db.Column(db.String(50), primary_key=True)
    subarea_id = db.Column(db.String(50), db.ForeignKey('sub_area.subarea_id'), nullable=False)
    tipo_sop = db.Column(db.String(20), nullable=False, default='regular')
    observacion_critica_sop = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('subarea_id', 'tipo_sop', name='uq_sop_subarea_tipo'),
    )

    subarea = db.relationship("SubArea", back_populates="sop")
    sop_fracciones = db.relationship("SopFraccion", back_populates="sop", cascade="all, delete-orphan", order_by="SopFraccion.orden")


# ======================================================
# 3. NIVELES DE LIMPIEZA
# ======================================================

class NivelLimpieza(db.Model):
    __tablename__ = 'nivel_limpieza'

    nivel_limpieza_id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String, nullable=False, unique=True)

    metodologias = db.relationship("Metodologia", back_populates="nivel_limpieza")
    sop_fraccion_detalles = db.relationship("SopFraccionDetalle", back_populates="nivel_limpieza")
    elemento_sets = db.relationship("ElementoSet", back_populates="nivel_limpieza")
    kits = db.relationship("Kit", back_populates="nivel_limpieza")


# ======================================================
# 4. FRACCIONES (CATÁLOGO UNIVERSAL)
# ======================================================
class Fraccion(db.Model):
    __tablename__ = 'fraccion'

    fraccion_id = db.Column(db.String, primary_key=True)
    fraccion_nombre = db.Column(db.String, nullable=False)
    nombre_custom = db.Column(db.String(200))  # ← NUEVO: variación opcional
    nota_tecnica = db.Column(db.Text)
    grupo_fracciones = db.Column(db.String(20), nullable=True)


    metodologias = db.relationship(
        "Metodologia",
        back_populates="fraccion",
        cascade="all, delete-orphan"
    )

    sop_fracciones = db.relationship("SopFraccion", back_populates="fraccion")
    elemento_sets = db.relationship("ElementoSet", back_populates="fraccion")
    kits = db.relationship("Kit", back_populates="fraccion", lazy="selectin")

    # ✅ NUEVA RELACIÓN 1:1 con instructivo_trabajo
    instructivo = db.relationship(
        "InstructivoTrabajo",
        back_populates="fraccion",
        uselist=False,  # ← Esto hace que sea 1:1
        cascade="all, delete-orphan"
    )

    # ✅ AGREGAR ESTO AL FINAL:
    @property
    def nombre_full(self):
        """Retorna nombre completo: base + custom (si existe)"""
        if self.nombre_custom:
            return f"{self.fraccion_nombre} — {self.nombre_custom}"
        return self.fraccion_nombre


# ======================================================
# 5. METODOLOGÍAS (por Fracción + Nivel) - PARA SOPs
# ======================================================
class MetodologiaBase(db.Model):
    __tablename__ = "metodologia_base"

    metodologia_base_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=True)
    descripcion = db.Column(db.Text, nullable=True)

    pasos = db.relationship(
        "MetodologiaBasePaso",
        back_populates="metodologia_base",
        cascade="all, delete-orphan",
        order_by="MetodologiaBasePaso.orden"
    )

    asignaciones = db.relationship(
        "Metodologia",
        back_populates="metodologia_base"
    )

class MetodologiaBasePaso(db.Model):
    __tablename__ = "metodologia_base_paso"

    metodologia_base_id = db.Column(
        db.String,
        db.ForeignKey("metodologia_base.metodologia_base_id"),
        primary_key=True
    )
    orden = db.Column(db.Integer, primary_key=True)
    instruccion = db.Column(db.Text, nullable=False)

    metodologia_base = db.relationship(
        "MetodologiaBase",
        back_populates="pasos"
    )

class Metodologia(db.Model):
    __tablename__ = "metodologia"

    fraccion_id = db.Column(
        db.String,
        db.ForeignKey("fraccion.fraccion_id"),
        primary_key=True
    )
    nivel_limpieza_id = db.Column(
        db.Integer,
        db.ForeignKey("nivel_limpieza.nivel_limpieza_id"),
        primary_key=True
    )

    metodologia_base_id = db.Column(
        db.String,
        db.ForeignKey("metodologia_base.metodologia_base_id"),
        nullable=False
    )

    fraccion = db.relationship("Fraccion", back_populates="metodologias")
    nivel_limpieza = db.relationship("NivelLimpieza", back_populates="metodologias")
    metodologia_base = db.relationship("MetodologiaBase", back_populates="asignaciones")


# ======================================================
# 6. SOP ARMADO (SOP -> FRACCIONES -> DETALLES POR NIVEL)
# ======================================================

class SopFraccion(db.Model):
    __tablename__ = 'sop_fraccion'
    __table_args__ = (
        db.UniqueConstraint('sop_id', 'fraccion_id', name='uq_sop_fraccion_unica'),
    )

    sop_fraccion_id = db.Column(db.String, primary_key=True)
    sop_id = db.Column(db.String, db.ForeignKey('sop.sop_id'), nullable=False, index=True)
    fraccion_id = db.Column(db.String, db.ForeignKey('fraccion.fraccion_id'), nullable=False, index=True)

    orden = db.Column(db.Integer, default=1)

    sop = db.relationship("SOP", back_populates="sop_fracciones")
    fraccion = db.relationship("Fraccion", back_populates="sop_fracciones")

    detalles = db.relationship(
        "SopFraccionDetalle",
        back_populates="sop_fraccion",
        cascade="all, delete-orphan"
    )


class SopFraccionDetalle(db.Model):
    __tablename__ = 'sop_fraccion_detalle'
    __table_args__ = (
        db.UniqueConstraint('sop_fraccion_id', 'nivel_limpieza_id', name='uq_sop_fraccion_detalle_nivel'),

        db.CheckConstraint(
            "(elemento_set_id IS NULL) OR (kit_id IS NULL AND receta_id IS NULL)",
            name="ck_sd_elementoset_vs_kit_receta"
        ),
    )

    sop_fraccion_detalle_id = db.Column(db.String, primary_key=True)

    sop_fraccion_id = db.Column(db.String, db.ForeignKey('sop_fraccion.sop_fraccion_id'), nullable=False, index=True)
    nivel_limpieza_id = db.Column(db.Integer, db.ForeignKey('nivel_limpieza.nivel_limpieza_id'), nullable=False, index=True)

    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'), nullable=True)
    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'), nullable=True)

    elemento_set_id = db.Column(db.String, db.ForeignKey('elemento_set.elemento_set_id'), nullable=True)

    consumo_id = db.Column(db.String, db.ForeignKey("consumo.consumo_id"), nullable=True)

    tiempo_unitario_min = db.Column(db.Float, nullable=True)

    sop_fraccion = db.relationship("SopFraccion", back_populates="detalles")
    nivel_limpieza = db.relationship("NivelLimpieza", back_populates="sop_fraccion_detalles")
    consumo = db.relationship("Consumo", back_populates="sop_fraccion_detalles")

    kit = db.relationship("Kit")
    receta = db.relationship("Receta")
    elemento_set = db.relationship("ElementoSet")


# ======================================================
# 7. HERRAMIENTAS Y KITS
# ======================================================

class Herramienta(db.Model):
    __tablename__ = 'herramienta'

    herramienta_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)
    descripcion = db.Column(db.Text)
    estatus = db.Column(db.String)

    kit_detalles = db.relationship("KitDetalle", back_populates="herramienta", cascade="all, delete-orphan")


class Kit(db.Model):
    __tablename__ = "kit"

    kit_id = db.Column(db.String, primary_key=True)
    fraccion_id = db.Column(db.String, db.ForeignKey("fraccion.fraccion_id"), nullable=True, index=True)  # ← NULLABLE para eventos
    nivel_limpieza_id = db.Column(db.Integer, db.ForeignKey("nivel_limpieza.nivel_limpieza_id"), nullable=True, index=True)
    nombre = db.Column(db.String, nullable=False)
    
    # NUEVO: tipo de kit
    tipo_kit = db.Column(db.String(20), default='sop', nullable=False)  # 'sop' | 'evento'

    # 🆕 NUEVO: Para filtrar kits de evento
    caso_id = db.Column(db.String(50), db.ForeignKey("caso_catalogo.caso_id"), nullable=True, index=True)

    fraccion = db.relationship("Fraccion", back_populates="kits")
    nivel_limpieza = db.relationship("NivelLimpieza", back_populates="kits")

    caso_catalogo = db.relationship("CasoCatalogo", back_populates="kits")
    detalles = db.relationship( "KitDetalle", back_populates="kit", cascade="all, delete-orphan", lazy="selectin",)

    __table_args__ = (
        db.CheckConstraint(
            "(tipo_kit = 'sop' AND fraccion_id IS NOT NULL AND caso_id IS NULL) OR "
            "(tipo_kit = 'evento' AND caso_id IS NOT NULL AND fraccion_id IS NULL)",
            name="ck_kit_tipo_consistency"
        ),
    )
    
    def __repr__(self):
        return f"<Kit {self.kit_id} tipo={self.tipo_kit} fr={self.fraccion_id} nivel={self.nivel_limpieza_id}>"
    



class KitDetalle(db.Model):
    __tablename__ = "kit_detalle"

    kit_id = db.Column(db.String, db.ForeignKey("kit.kit_id"), primary_key=True)
    herramienta_id = db.Column(db.String, db.ForeignKey("herramienta.herramienta_id"), primary_key=True)
    nota = db.Column(db.String, nullable=True)

    kit = db.relationship("Kit", back_populates="detalles")
    herramienta = db.relationship("Herramienta")

    def __repr__(self):
        return f"<KitDetalle {self.kit_id} {self.herramienta_id}>"


# ======================================================
# 8. RECETAS Y QUÍMICOS
# ======================================================

class Quimico(db.Model):
    __tablename__ = 'quimico'

    quimico_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)
    categoria = db.Column(db.String)
    presentacion = db.Column(db.String)
    unidad_base = db.Column(db.String)

    detalles = db.relationship("RecetaDetalle", back_populates="quimico", cascade="all, delete-orphan")


class Receta(db.Model):
    __tablename__ = 'receta'

    receta_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)

    detalles = db.relationship("RecetaDetalle", back_populates="receta", cascade="all, delete-orphan")


class RecetaDetalle(db.Model):
    __tablename__ = 'receta_detalle'

    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'), primary_key=True)
    quimico_id = db.Column(db.String, db.ForeignKey('quimico.quimico_id'), primary_key=True)

    dosis = db.Column(db.Float)
    unidad_dosis = db.Column(db.String)

    volumen_base = db.Column(db.Float)
    unidad_volumen = db.Column(db.String)

    nota = db.Column(db.String)

    receta = db.relationship("Receta", back_populates="detalles")
    quimico = db.relationship("Quimico", back_populates="detalles")


class Consumo(db.Model):
    __tablename__ = "consumo"

    consumo_id = db.Column(db.String, primary_key=True)

    valor = db.Column(db.Float, nullable=True)
    unidad = db.Column(db.String, nullable=True)
    regla = db.Column(db.String, nullable=True)

    sop_fraccion_detalles = db.relationship("SopFraccionDetalle", back_populates="consumo")
    elemento_detalles = db.relationship("ElementoDetalle", back_populates="consumo")


# ======================================================
# 9. ELEMENTOS / SETS
# ======================================================

class Elemento(db.Model):
    __tablename__ = 'elemento'

    elemento_id = db.Column(db.String, primary_key=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False, index=True)

    nombre = db.Column(db.String, nullable=False)
    cantidad = db.Column(db.Float)
    estatus = db.Column(db.String)
    descripcion = db.Column(db.Text, nullable=True)

    subarea = db.relationship("SubArea", back_populates="elementos")


class ElementoSet(db.Model):
    __tablename__ = 'elemento_set'

    elemento_set_id = db.Column(db.String, primary_key=True)

    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False, index=True)
    fraccion_id = db.Column(db.String, db.ForeignKey('fraccion.fraccion_id'), nullable=False, index=True)
    nivel_limpieza_id = db.Column(db.Integer, db.ForeignKey('nivel_limpieza.nivel_limpieza_id'), nullable=False, index=True)

    nombre = db.Column(db.String, nullable=False)

    subarea = db.relationship("SubArea", back_populates="elemento_sets")
    fraccion = db.relationship("Fraccion", back_populates="elemento_sets")
    nivel_limpieza = db.relationship("NivelLimpieza", back_populates="elemento_sets")

    detalles = db.relationship(
        "ElementoDetalle",
        back_populates="elemento_set",
        cascade="all, delete-orphan",
        order_by="ElementoDetalle.orden"
    )


class ElementoDetalle(db.Model):
    __tablename__ = 'elemento_detalle'
    __table_args__ = (
        db.UniqueConstraint('elemento_set_id', 'elemento_id', name='uq_elemento_set_elemento'),
    )

    elemento_set_id = db.Column(db.String, db.ForeignKey('elemento_set.elemento_set_id'), primary_key=True)
    elemento_id = db.Column(db.String, db.ForeignKey('elemento.elemento_id'), primary_key=True)

    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'), nullable=True)
    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'), nullable=True)
    consumo_id = db.Column(db.String, db.ForeignKey("consumo.consumo_id"), nullable=True)
    orden = db.Column(db.Integer, nullable=False, default=1000)

    elemento_set = db.relationship("ElementoSet", back_populates="detalles")
    consumo = db.relationship("Consumo", back_populates="elemento_detalles")
    elemento = db.relationship("Elemento")
    receta = db.relationship("Receta")
    kit = db.relationship("Kit")


# ======================================================
# 10. PERSONAL Y ASIGNACIÓN BASE
# ======================================================

class Personal(db.Model):
    __tablename__ = 'personal'

    personal_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)

    asignaciones = db.relationship("AsignacionPersonal", back_populates="personal", cascade="all, delete-orphan")


class AsignacionPersonal(db.Model):
    __tablename__ = 'asignacion_personal'

    asignacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    personal_id = db.Column(db.String, db.ForeignKey('personal.personal_id'), nullable=False, index=True)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), nullable=False, index=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False, index=True)

    nivel_limpieza_asignado = db.Column(db.String, nullable=False)

    personal = db.relationship("Personal", back_populates="asignaciones")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")


# ======================================================
# 11. EVENTOS Y TAREAS ESPECIALES (NUEVO)
# ======================================================

class EventoCatalogo(db.Model):
    __tablename__ = 'evento_catalogo'
    
    evento_tipo_id = db.Column(db.String(20), primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    
    casos = db.relationship("CasoCatalogo", back_populates="evento_catalogo")
    sop_eventos = db.relationship("SopEvento", back_populates="evento_catalogo")

class CasoCatalogo(db.Model):
    __tablename__ = 'caso_catalogo'
    
    caso_id = db.Column(db.String(30), primary_key=True)
    evento_tipo_id = db.Column(db.String(20), db.ForeignKey('evento_catalogo.evento_tipo_id'), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    
    evento_catalogo = db.relationship("EventoCatalogo", back_populates="casos")
    kits = db.relationship("Kit", back_populates="caso_catalogo", lazy="selectin")



# ======================================================
# 12. LANZAMIENTO (SEMANA / DÍA / TAREAS)
# ======================================================

class LanzamientoSemana(db.Model):
    __tablename__ = 'lanzamiento_semana'

    semana_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String)
    fecha_inicio = db.Column(db.Date, nullable=False)

    dias = db.relationship("LanzamientoDia", back_populates="semana", cascade="all, delete-orphan")


class LanzamientoDia(db.Model):
    __tablename__ = 'lanzamiento_dia'

    dia_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    semana_id = db.Column(db.Integer, db.ForeignKey('lanzamiento_semana.semana_id'), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)

    semana = db.relationship("LanzamientoSemana", back_populates="dias")
    tareas = db.relationship("LanzamientoTarea", back_populates="dia", cascade="all, delete-orphan")


class LanzamientoTarea(db.Model):
    __tablename__ = 'lanzamiento_tarea'

    tarea_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    dia_id = db.Column(db.Integer, db.ForeignKey('lanzamiento_dia.dia_id'), nullable=False)
    personal_id = db.Column(db.String(50), db.ForeignKey('personal.personal_id'), nullable=False)
    
    # Campos opcionales (NULL para tareas fijas: inicio, receso)
    area_id = db.Column(db.String(50), db.ForeignKey('area.area_id'), nullable=True)
    subarea_id = db.Column(db.String(50), db.ForeignKey('sub_area.subarea_id'), nullable=True)
    sop_id = db.Column(db.String(50), db.ForeignKey('sop.sop_id'), nullable=True)
    nivel_limpieza_asignado = db.Column(db.String(20), nullable=True)
    
    # NUEVO: Para eventos configurados
    sop_evento_id = db.Column(db.String(50), db.ForeignKey('sop_evento.sop_evento_id'), nullable=True)
    
    # Campos de control
    es_adicional = db.Column(db.Boolean, default=False)
    orden = db.Column(db.Integer, default=0)
    
    # Tipo de tarea
    tipo_tarea = db.Column(db.String(20), default='sop', nullable=False)
    # Valores: 'sop' | 'inicio' | 'receso' | 'evento'
    
    es_arrastrable = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('dia_id', 'subarea_id', 'sop_id', name='uq_tarea_dia_subarea_sop'),
    )

    # Relaciones
    dia = db.relationship("LanzamientoDia", back_populates="tareas")
    personal = db.relationship("Personal", lazy="joined")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")
    sop = db.relationship("SOP")
    sop_evento = db.relationship("SopEvento", back_populates="lanzamientos")


# ======================================================
# 13. PLANTILLAS SEMANALES
# ======================================================

class PlantillaSemanal(db.Model):
    __tablename__ = 'plantilla_semanal'

    plantilla_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String, unique=True, nullable=False)
    creada_en = db.Column(db.DateTime, default=now_cdmx)

    items = db.relationship("PlantillaItem", back_populates="plantilla", cascade="all, delete-orphan")
    semanas_aplicadas = db.relationship("PlantillaSemanaAplicada", back_populates="plantilla")


class PlantillaItem(db.Model):
    __tablename__ = 'plantilla_item'

    item_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plantilla_id = db.Column(db.Integer, db.ForeignKey('plantilla_semanal.plantilla_id'), nullable=False)
    dia_index = db.Column(db.Integer, nullable=False)
    personal_id = db.Column(db.String(50), db.ForeignKey('personal.personal_id'), nullable=False)
    area_id = db.Column(db.String(50), db.ForeignKey('area.area_id'), nullable=False)
    subarea_id = db.Column(db.String(50), db.ForeignKey('sub_area.subarea_id'), nullable=False)
    sop_id = db.Column(db.String(50), db.ForeignKey('sop.sop_id'), nullable=True)
    nivel_limpieza_asignado = db.Column(db.String(20))
    es_adicional = db.Column(db.Boolean, default=False)
    orden = db.Column(db.Integer, default=0)

    plantilla = db.relationship("PlantillaSemanal", back_populates="items")
    personal = db.relationship("Personal", lazy="joined")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")
    sop = db.relationship("SOP")


class PlantillaSemanaAplicada(db.Model):
    __tablename__ = 'plantilla_semana_aplicada'

    semana_lunes = db.Column(db.Date, primary_key=True)
    plantilla_id = db.Column(db.Integer, db.ForeignKey('plantilla_semanal.plantilla_id'))
    aplicada_en = db.Column(db.DateTime, default=now_cdmx)

    plantilla = db.relationship("PlantillaSemanal", back_populates="semanas_aplicadas")


# ======================================================
# 14. USUARIOS Y AUTENTICACIÓN
# ======================================================

class User(db.Model, UserMixin):
    __tablename__ = "user"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(20), nullable=False, default="operativo", index=True)

    personal_id = db.Column(
        db.String,
        db.ForeignKey("personal.personal_id"),
        nullable=True,
        unique=True,
        index=True
    )
    personal = db.relationship("Personal", lazy="joined")

    created_at = db.Column(db.DateTime, default=now_cdmx)

    def get_id(self):
        return str(self.user_id)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)


# ======================================================
# 15. CHECKS DE TAREAS (Operativo marca subárea completada)
# ======================================================

class TareaCheck(db.Model):
    __tablename__ = 'tarea_check'
    
    check_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tarea_id = db.Column(
        db.Integer, 
        db.ForeignKey('lanzamiento_tarea.tarea_id', ondelete='CASCADE'), 
        nullable=False, 
        unique=True,
        index=True
    )
    
    checked_at = db.Column(db.DateTime, nullable=False)
    
    user_id = db.Column(
        db.Integer, 
        db.ForeignKey('user.user_id'), 
        nullable=False,
        index=True
    )
    
    tarea = db.relationship(
        "LanzamientoTarea", 
        backref=db.backref("check", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    )
    user = db.relationship("User")
    
    def __repr__(self):
        return f"<TareaCheck tarea={self.tarea_id} at={self.checked_at}>"


# ============================================================================
# NUEVOS MODELOS PARA SISTEMA DE EVENTOS
# ============================================================================
# ============================================================================
# 1. SopEventoFraccion - Pool de fracciones reutilizables
# ============================================================================
class SopEventoFraccion(db.Model):
    __tablename__ = 'sop_evento_fraccion'
    
    fraccion_evento_id = db.Column(db.String(50), primary_key=True)
    
    # ✅ NUEVA COLUMNA
    evento_tipo_id = db.Column(db.String(20),
                               db.ForeignKey('evento_catalogo.evento_tipo_id'),
                               nullable=False)
    
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    
    # Relaciones
    evento_catalogo = db.relationship("EventoCatalogo",
                                     foreign_keys=[evento_tipo_id])
    
    metodologia = db.relationship("MetodologiaEventoFraccion", 
                                 back_populates="fraccion", 
                                 uselist=False,
                                 cascade="all, delete-orphan")
    
    detalles_sop = db.relationship("SopEventoDetalle", 
                                   back_populates="fraccion")

    def __repr__(self):
        return f'<SopEventoFraccion {self.fraccion_evento_id}: {self.nombre}>'
    

# ============================================================================
# 2. MetodologiaEventoFraccion - Metodología 1:1 con cada fracción
# ============================================================================
class MetodologiaEventoFraccion(db.Model):
    __tablename__ = 'metodologia_evento_fraccion'
    
    metodologia_fraccion_id = db.Column(db.String(50), primary_key=True)
    # Formato: MEF-XX-001 (tú defines el código manualmente)
    
    fraccion_evento_id = db.Column(db.String(50), 
                                   db.ForeignKey('sop_evento_fraccion.fraccion_evento_id'),
                                   nullable=False, 
                                   unique=True)
    
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    
    # Relaciones
    fraccion = db.relationship("SopEventoFraccion", 
                              back_populates="metodologia")
    
    pasos = db.relationship("MetodologiaEventoFraccionPaso", 
                           back_populates="metodologia",
                           order_by="MetodologiaEventoFraccionPaso.numero_paso",
                           cascade="all, delete-orphan")

    def __repr__(self):
        return f'<MetodologiaEventoFraccion {self.metodologia_fraccion_id}: {self.nombre}>'
    

# ============================================================================
# 3. MetodologiaEventoFraccionPaso - Pasos de cada metodología
# ============================================================================
class MetodologiaEventoFraccionPaso(db.Model):
    __tablename__ = 'metodologia_evento_fraccion_paso'
    
    paso_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    metodologia_fraccion_id = db.Column(db.String(50),
                                       db.ForeignKey('metodologia_evento_fraccion.metodologia_fraccion_id'),
                                       nullable=False)
    
    numero_paso = db.Column(db.Integer, nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    
    
    # Relaciones
    metodologia = db.relationship("MetodologiaEventoFraccion", 
                                 back_populates="pasos")
    
    __table_args__ = (
        db.UniqueConstraint('metodologia_fraccion_id', 'numero_paso',
                          name='uq_metodologia_fraccion_paso'),
    )

    def __repr__(self):
        return f'<MetodologiaEventoFraccionPaso {self.metodologia_fraccion_id} - Paso {self.numero_paso}>'


#============================================================================
# 4. SopEvento - SOP configurado para cada Evento-Caso
# ============================================================================
class SopEvento(db.Model):
    __tablename__ = 'sop_evento'
    
    sop_evento_id = db.Column(db.String(50), primary_key=True)
    # Formato: SE-XX-YY-001 (tú defines el código manualmente)
    
    evento_tipo_id = db.Column(db.String(20),
                               db.ForeignKey('evento_catalogo.evento_tipo_id'),
                               nullable=False)
    
    caso_id = db.Column(db.String(30),
                       db.ForeignKey('caso_catalogo.caso_id'),
                       nullable=False)
    
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    
    # Relaciones
    evento_catalogo = db.relationship("EventoCatalogo", 
                                     foreign_keys=[evento_tipo_id])
    
    caso_catalogo = db.relationship("CasoCatalogo", 
                                   foreign_keys=[caso_id])
    
    detalles = db.relationship("SopEventoDetalle", 
                              back_populates="sop_evento",
                              order_by="SopEventoDetalle.orden",
                              cascade="all, delete-orphan")
    
    lanzamientos = db.relationship("LanzamientoTarea",
                                  back_populates="sop_evento")
    
    __table_args__ = (
        db.UniqueConstraint('evento_tipo_id', 'caso_id', 
                          name='uq_sop_evento_tipo_caso'),
    )

    def __repr__(self):
        return f'<SopEvento {self.sop_evento_id}: {self.nombre}>'


# ============================================================================
# 5. SopEventoDetalle - Fracciones configuradas en el SOP
# ============================================================================
class SopEventoDetalle(db.Model):
    __tablename__ = 'sop_evento_detalle'
    
    detalle_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    sop_evento_id = db.Column(db.String(50),
                             db.ForeignKey('sop_evento.sop_evento_id'),
                             nullable=False)
    
    fraccion_evento_id = db.Column(db.String(50),
                                  db.ForeignKey('sop_evento_fraccion.fraccion_evento_id'),
                                  nullable=False)
    
    orden = db.Column(db.Integer, nullable=False)
    tiempo_estimado = db.Column(db.Integer, nullable=False)  # minutos
    
    # Opcionales: Kit, Receta, Consumo
    kit_id = db.Column(db.String(50), 
                      db.ForeignKey('kit.kit_id'), 
                      nullable=True)
    
    receta_id = db.Column(db.String(50), 
                         db.ForeignKey('receta.receta_id'), 
                         nullable=True)
    
    consumo_id = db.Column(db.String(50), 
                          db.ForeignKey('consumo.consumo_id'), 
                          nullable=True)
    
    observaciones = db.Column(db.Text)
    
    # Relaciones
    sop_evento = db.relationship("SopEvento", 
                                back_populates="detalles")
    
    fraccion = db.relationship("SopEventoFraccion", 
                              back_populates="detalles_sop")
    
    kit = db.relationship("Kit")
    receta = db.relationship("Receta")
    consumo = db.relationship("Consumo")
    
    __table_args__ = (
        db.UniqueConstraint('sop_evento_id', 'fraccion_evento_id',
                          name='uq_sop_evento_fraccion'),
        db.UniqueConstraint('sop_evento_id', 'orden',
                          name='uq_sop_evento_orden'),
    )

    def __repr__(self):
        return f'<SopEventoDetalle SOP:{self.sop_evento_id} Fracción:{self.fraccion_evento_id} Orden:{self.orden}>'
    

class InstructivoTrabajo(db.Model):
    __tablename__ = 'instructivo_trabajo'
    
    instructivo_id = db.Column(db.Integer, primary_key=True)
    fraccion_id = db.Column(
        db.String,
        db.ForeignKey('fraccion.fraccion_id', ondelete='CASCADE'),
        nullable=False,
        unique=True
    )
    codigo = db.Column(db.String(50), unique=True, nullable=False) 
    instructivo_nombre = db.Column(db.String(200), nullable=False)
    instructivo_url = db.Column(db.String(500), nullable=False)
    
    # Relaciones
    fraccion = db.relationship("Fraccion", back_populates="instructivo")
    relaciones = db.relationship(
        "InstructivoRelacion",
        back_populates="instructivo",
        cascade="all, delete-orphan"
    )

class TMO(db.Model):
    __tablename__ = 'tmo'
    
    tmo_id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String, unique=True, nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    url_instructivo = db.Column(db.String(500), nullable=False)
    
    # Relación inversa
    relaciones = db.relationship(
        "InstructivoRelacion",
        back_populates="tmo"
    )

class HerramientaUso(db.Model):
    __tablename__ = 'herramienta_uso'
    
    herramienta_uso_id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    codigo = db.Column(db.String, unique=True, nullable=False)
    url_instructivo = db.Column(db.String(500), nullable=False)
    
    # Relación inversa con nombre específico
    relaciones = db.relationship(
        "InstructivoRelacion",
        back_populates="herramienta_uso"  # ← Nombre único
    )

class FichaReceta(db.Model):
    __tablename__ = 'ficha_receta'
    
    ficha_receta_id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String, unique=True, nullable=False)
    nombre = db.Column(db.String(200), nullable=False)
    url_instructivo = db.Column(db.String(500), nullable=False)
    
    # Relación inversa
    relaciones = db.relationship(
        "InstructivoRelacion",
        back_populates="ficha_receta"
    )

class InstructivoRelacion(db.Model):
    __tablename__ = 'instructivo_relacion'
    
    # PK única de esta tabla
    id = db.Column(db.Integer, primary_key=True)
    
    # FK hacia instructivo_trabajo ← AQUÍ ESTÁ
    instructivo_id = db.Column(
        db.Integer,
        db.ForeignKey('instructivo_trabajo.instructivo_id', ondelete='CASCADE'),
        nullable=False
    )
    
    # FK hacia tmo (nullable)
    tmo_id = db.Column(
        db.Integer,
        db.ForeignKey('tmo.tmo_id', ondelete='CASCADE'),
        nullable=True
    )
    
    # FK hacia herramienta_uso (nullable)
    herramienta_uso_id = db.Column(
        db.Integer,
        db.ForeignKey('herramienta_uso.herramienta_uso_id', ondelete='CASCADE'),
        nullable=True
    )
    
    # FK hacia ficha_receta (nullable)
    ficha_receta_id = db.Column(
        db.Integer,
        db.ForeignKey('ficha_receta.ficha_receta_id', ondelete='CASCADE'),
        nullable=True
    )
    
    tipo = db.Column(db.String(20), nullable=False)
    orden = db.Column(db.Integer, default=0)
    
    # Relaciones
    instructivo = db.relationship("InstructivoTrabajo", back_populates="relaciones")
    tmo = db.relationship("TMO", back_populates="relaciones")
    herramienta_uso = db.relationship("HerramientaUso", back_populates="relaciones")
    ficha_receta = db.relationship("FichaReceta", back_populates="relaciones")
