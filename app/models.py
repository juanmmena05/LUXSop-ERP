from datetime import datetime
from .extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# ======================================================
# 1. ÁREAS Y SUBÁREAS
# ======================================================

class Area(db.Model):
    __tablename__ = 'area'

    area_id = db.Column(db.String, primary_key=True)
    area_nombre = db.Column(db.String, nullable=False)
    tipo_area = db.Column(db.String)
    cantidad_subareas = db.Column(db.Integer)
    orden_area = db.Column(db.Integer, default=1000)

    subareas = db.relationship(
        "SubArea",
        back_populates="area",
        cascade="all, delete-orphan"
    )


class SubArea(db.Model):
    __tablename__ = 'sub_area'

    subarea_id = db.Column(db.String, primary_key=True)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), nullable=False, index=True)

    subarea_nombre = db.Column(db.String, nullable=False)
    superficie_subarea = db.Column(db.Float)
    frecuencia = db.Column(db.Float)
    orden_subarea = db.Column(db.Integer, default=1000)

    area = db.relationship("Area", back_populates="subareas")

    # Idealmente: 1 SOP por SubArea (tu formato SP-<SUBAREA>)
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
    __table_args__ = (
        # 1 SOP por subárea
        db.UniqueConstraint('subarea_id', name='uq_sop_subarea'),
    )

    sop_id = db.Column(db.String, primary_key=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False, index=True)
    observacion_critica_sop = db.Column(db.Text)

    subarea = db.relationship("SubArea", back_populates="sop")

    sop_fracciones = db.relationship(
        "SopFraccion",
        back_populates="sop",
        cascade="all, delete-orphan",
        order_by="SopFraccion.orden"
    )


# ======================================================
# 3. NIVELES DE LIMPIEZA (SIN factor)
# ======================================================

class NivelLimpieza(db.Model):
    __tablename__ = 'nivel_limpieza'

    nivel_limpieza_id = db.Column(db.Integer, primary_key=True)  # 1/2/3
    nombre = db.Column(db.String, nullable=False, unique=True)   # basica/media/profunda

    metodologias = db.relationship("Metodologia", back_populates="nivel_limpieza")
    sop_fraccion_detalles = db.relationship("SopFraccionDetalle", back_populates="nivel_limpieza")
    elemento_sets = db.relationship("ElementoSet", back_populates="nivel_limpieza")
    kits = db.relationship("Kit", back_populates="nivel_limpieza")



# ======================================================
# 4. FRACCIONES (CATÁLOGO UNIVERSAL)
# ======================================================

class Fraccion(db.Model):
    __tablename__ = 'fraccion'

    fraccion_id = db.Column(db.String, primary_key=True)  # FR-XX-###
    fraccion_nombre = db.Column(db.String, nullable=False)
    nota_tecnica = db.Column(db.Text)

    metodologias = db.relationship(
        "Metodologia",
        back_populates="fraccion",
        cascade="all, delete-orphan"
    )

    sop_fracciones = db.relationship("SopFraccion", back_populates="fraccion")

    elemento_sets = db.relationship("ElementoSet", back_populates="fraccion")

    kits = db.relationship("Kit", back_populates="fraccion", lazy="selectin")



# ======================================================
# 5. METODOLOGÍAS (por Fracción + Nivel)
# ======================================================
class MetodologiaBase(db.Model):
    __tablename__ = "metodologia_base"

    metodologia_base_id = db.Column(db.String, primary_key=True)  # MB-XX-###
    nombre = db.Column(db.String, nullable=True)  # opcional (UI)
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

    sop_fraccion_id = db.Column(db.String, primary_key=True)  # SF-...
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
        # 1 detalle por nivel por cada SopFraccion
        db.UniqueConstraint('sop_fraccion_id', 'nivel_limpieza_id', name='uq_sop_fraccion_detalle_nivel'),

        # Regla: si hay elemento_set → NO debe haber kit/receta en este detalle
        db.CheckConstraint(
            "(elemento_set_id IS NULL) OR (kit_id IS NULL AND receta_id IS NULL)",
            name="ck_sd_elementoset_vs_kit_receta"
        ),
    )

    sop_fraccion_detalle_id = db.Column(db.String, primary_key=True)  # SD-...

    sop_fraccion_id = db.Column(db.String, db.ForeignKey('sop_fraccion.sop_fraccion_id'), nullable=False, index=True)
    nivel_limpieza_id = db.Column(db.Integer, db.ForeignKey('nivel_limpieza.nivel_limpieza_id'), nullable=False, index=True)

    # Opción A (sin elementos): kit/receta pueden ir aquí (uno o ambos)
    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'), nullable=True)
    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'), nullable=True)

    # Opción B (con elementos): elemento_set_id va aquí y kit/receta deben ser NULL
    elemento_set_id = db.Column(db.String, db.ForeignKey('elemento_set.elemento_set_id'), nullable=True)

    # Consumo directo a la Fraccion realizada
    consumo_id = db.Column(db.String, db.ForeignKey("consumo.consumo_id"), nullable=True)

    # tiempo ES de la fracción (como tú dijiste), lo guardamos aquí por nivel
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


from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship

class Kit(db.Model):
    __tablename__ = "kit"

    kit_id = db.Column(db.String, primary_key=True)  # ej: KT-TL-001
    fraccion_id = db.Column(db.String, db.ForeignKey("fraccion.fraccion_id"), nullable=False, index=True)
    nivel_limpieza_id = db.Column(db.Integer, db.ForeignKey("nivel_limpieza.nivel_limpieza_id"), nullable=True, index=True)
    nombre = db.Column(db.String, nullable=False)

    fraccion = db.relationship("Fraccion", back_populates="kits")
    nivel_limpieza = db.relationship("NivelLimpieza", back_populates="kits")

    detalles = db.relationship(
        "KitDetalle",
        back_populates="kit",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self):
        return f"<Kit {self.kit_id} fr={self.fraccion_id} nivel={self.nivel_limpieza_id}>"



class KitDetalle(db.Model):
    __tablename__ = "kit_detalle"

    kit_id = Column(String, ForeignKey("kit.kit_id"), primary_key=True)
    herramienta_id = Column(String, ForeignKey("herramienta.herramienta_id"), primary_key=True)
    nota = Column(String, nullable=True)

    kit = relationship("Kit", back_populates="detalles")
    herramienta = relationship("Herramienta")

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
    # EJ: CM-DS-003

    valor = db.Column(db.Float, nullable=True)     
    unidad = db.Column(db.String, nullable=True)   
    regla = db.Column(db.String, nullable=True)    
    # ej: "= 3 mL", "por m2", etc.

    sop_fraccion_detalles = db.relationship( "SopFraccionDetalle", back_populates="consumo")
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

    elemento_set_id = db.Column(db.String, primary_key=True)  # ES-...

    # Tus columnas de control (clave para tu método de trabajo)
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
# (lo dejo igual a tu versión para no romper tu app)
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

    # Si luego quieres, esto lo migramos a FK a nivel_limpieza
    nivel_limpieza_asignado = db.Column(db.String, nullable=False)  # “basica”, “media”, “profunda”

    personal = db.relationship("Personal", back_populates="asignaciones")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")


# ======================================================
# 11. LANZAMIENTO (SEMANA / DÍA / TAREAS)
# ======================================================

class LanzamientoSemana(db.Model):
    __tablename__ = 'lanzamiento_semana'

    semana_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String)
    fecha_inicio = db.Column(db.Date, nullable=False)  # lunes de la semana

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
    __table_args__ = (
        db.UniqueConstraint('dia_id', 'subarea_id', name='uq_tarea_dia_subarea'),
    )

    tarea_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    dia_id = db.Column(db.Integer, db.ForeignKey('lanzamiento_dia.dia_id'), nullable=False, index=True)
    personal_id = db.Column(db.String, db.ForeignKey('personal.personal_id'), nullable=False, index=True)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), nullable=False, index=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False, index=True)

    nivel_limpieza_asignado = db.Column(db.String, nullable=False)

    dia = db.relationship("LanzamientoDia", back_populates="tareas")
    personal = db.relationship("Personal", lazy="joined")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")


# ======================================================
# 12. PLANTILLAS SEMANALES
# ======================================================

class PlantillaSemanal(db.Model):
    __tablename__ = 'plantilla_semanal'

    plantilla_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String, unique=True, nullable=False)
    creada_en = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("PlantillaItem", back_populates="plantilla", cascade="all, delete-orphan")
    semanas_aplicadas = db.relationship("PlantillaSemanaAplicada", back_populates="plantilla")


class PlantillaItem(db.Model):
    __tablename__ = 'plantilla_item'

    item_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    plantilla_id = db.Column(db.Integer, db.ForeignKey('plantilla_semanal.plantilla_id'), nullable=False)
    dia_index = db.Column(db.Integer, nullable=False)  # 0 = Lunes ... 5 = Sábado

    personal_id = db.Column(db.String, db.ForeignKey('personal.personal_id'), nullable=False)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), nullable=False)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False)
    nivel_limpieza_asignado = db.Column(db.String, nullable=False)

    plantilla = db.relationship("PlantillaSemanal", back_populates="items")
    personal = db.relationship("Personal", lazy="joined")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")


class PlantillaSemanaAplicada(db.Model):
    __tablename__ = 'plantilla_semana_aplicada'

    semana_lunes = db.Column(db.Date, primary_key=True)  # lunes de la semana
    plantilla_id = db.Column(db.Integer, db.ForeignKey('plantilla_semanal.plantilla_id'))
    aplicada_en = db.Column(db.DateTime, default=datetime.utcnow)

    plantilla = db.relationship("PlantillaSemanal", back_populates="semanas_aplicadas")


class User(db.Model, UserMixin):
    __tablename__ = "user"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # "admin" | "operativo"
    role = db.Column(db.String(20), nullable=False, default="operativo", index=True)

    # Solo operativos: liga a Personal
    personal_id = db.Column(
        db.String,
        db.ForeignKey("personal.personal_id"),
        nullable=True,
        unique=True,   # evita dos usuarios para el mismo Personal
        index=True
    )
    personal = db.relationship("Personal", lazy="joined")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        return str(self.user_id)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)