from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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

    subareas = db.relationship("SubArea", back_populates="area")


class SubArea(db.Model):
    __tablename__ = 'sub_area'

    subarea_id = db.Column(db.String, primary_key=True)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), nullable=False, index=True)

    subarea_nombre = db.Column(db.String, nullable=False)
    superficie_subarea = db.Column(db.Float)
    nivel_limpieza = db.Column(db.String)
    frecuencia = db.Column(db.Float)
    orden_subarea = db.Column(db.Integer, default=1000)

    area = db.relationship("Area", back_populates="subareas")
    sops = db.relationship("SOP", back_populates="subarea")
    elementos = db.relationship("Elemento", back_populates="subarea")


# ======================================================
# 2. SOP (STANDARD OPERATING PROCEDURE)
# ======================================================

class SOP(db.Model):
    __tablename__ = 'sop'

    sop_id = db.Column(db.String, primary_key=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False, index=True)
    sop_codigo = db.Column(db.String)
    observacion_critica_sop = db.Column(db.Text)

    subarea = db.relationship("SubArea", back_populates="sops")
    fracciones = db.relationship("Fraccion", back_populates="sop")


# ======================================================
# 3. NIVELES DE LIMPIEZA
# ======================================================

class NivelLimpieza(db.Model):
    __tablename__ = 'nivel_limpieza'

    nivel_limpieza_id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String, nullable=False)
    factor_nivel = db.Column(db.Float, nullable=False)


# ======================================================
# 4. METODOLOGÍAS
# ======================================================

class Metodologia(db.Model):
    __tablename__ = 'metodologia'

    metodologia_id = db.Column(db.String, primary_key=True)
    nivel_limpieza_id = db.Column(db.Integer, db.ForeignKey('nivel_limpieza.nivel_limpieza_id'), nullable=False)

    nombre = db.Column(db.String, nullable=False)
    descripcion = db.Column(db.Text)

    nivel_limpieza = db.relationship("NivelLimpieza")
    pasos = db.relationship("MetodologiaPasos", back_populates="metodologia")


class MetodologiaPasos(db.Model):
    __tablename__ = 'metodologia_pasos'

    metodologia_id = db.Column(db.String, db.ForeignKey('metodologia.metodologia_id'), primary_key=True)
    orden = db.Column(db.Integer, primary_key=True)
    instruccion = db.Column(db.Text)

    metodologia = db.relationship("Metodologia", back_populates="pasos")


# ======================================================
# 5. FRACCIONES Y DETALLES
# ======================================================

class Fraccion(db.Model):
    __tablename__ = 'fraccion'

    fraccion_id = db.Column(db.String, primary_key=True)
    sop_id = db.Column(db.String, db.ForeignKey('sop.sop_id'), nullable=False, index=True)

    fraccion_nombre = db.Column(db.String, nullable=False)
    descripcion = db.Column(db.Text)
    nota_tecnica = db.Column(db.Text)
    unidad_medida = db.Column(db.String)
    tiempo_base_min = db.Column(db.Float, default=0)
    tipo_formula = db.Column(db.String)
    orden = db.Column(db.Integer, default=1)

    sop = db.relationship("SOP", back_populates="fracciones")
    detalles = db.relationship("FraccionDetalle", back_populates="fraccion")


class FraccionDetalle(db.Model):
    __tablename__ = 'fraccion_detalle'

    fraccion_detalle_id = db.Column(db.String, primary_key=True)
    fraccion_id = db.Column(db.String, db.ForeignKey('fraccion.fraccion_id'), nullable=False, index=True)
    elemento_set_id = db.Column(db.String, db.ForeignKey('elemento_set.elemento_set_id'))
    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'))
    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'))
    nivel_limpieza_id = db.Column(db.Integer, db.ForeignKey('nivel_limpieza.nivel_limpieza_id'), nullable=False)
    metodologia_id = db.Column(db.String, db.ForeignKey('metodologia.metodologia_id'), nullable=False)
    ajuste_factor = db.Column(db.Float, default=1.0)

    fraccion = db.relationship("Fraccion", back_populates="detalles")
    elemento_set = db.relationship("ElementoSet")
    receta = db.relationship("Receta")
    kit = db.relationship("Kit")
    metodologia = db.relationship("Metodologia")
    nivel_limpieza = db.relationship("NivelLimpieza")


# ======================================================
# 6. HERRAMIENTAS Y KITS
# ======================================================

class Herramienta(db.Model):
    __tablename__ = 'herramienta'

    herramienta_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)
    descripcion = db.Column(db.Text)
    estatus = db.Column(db.String)

    kit_detalles = db.relationship("KitDetalle", back_populates="herramienta")


class Kit(db.Model):
    __tablename__ = 'kit'

    kit_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)

    detalles = db.relationship("KitDetalle", back_populates="kit")


class KitDetalle(db.Model):
    __tablename__ = 'kit_detalle'

    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'), primary_key=True)
    herramienta_id = db.Column(db.String, db.ForeignKey('herramienta.herramienta_id'), primary_key=True)

    color = db.Column(db.String)
    nota = db.Column(db.String)

    kit = db.relationship("Kit", back_populates="detalles")
    herramienta = db.relationship("Herramienta", back_populates="kit_detalles")


# ======================================================
# 7. RECETAS Y QUÍMICOS
# ======================================================

class Quimico(db.Model):
    __tablename__ = 'quimico'

    quimico_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)
    categoria = db.Column(db.String)
    presentacion = db.Column(db.String)
    unidad_base = db.Column(db.String)

    detalles = db.relationship("RecetaDetalle", back_populates="quimico")


class Receta(db.Model):
    __tablename__ = 'receta'

    receta_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)

    detalles = db.relationship("RecetaDetalle", back_populates="receta")


class RecetaDetalle(db.Model):
    __tablename__ = 'receta_detalle'

    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'), primary_key=True)
    quimico_id = db.Column(db.String, db.ForeignKey('quimico.quimico_id'), primary_key=True)

    dosis = db.Column(db.Float)
    unidad_dosis = db.Column(db.String)
    nota = db.Column(db.String)

    receta = db.relationship("Receta", back_populates="detalles")
    quimico = db.relationship("Quimico", back_populates="detalles")


# ======================================================
# 8. ELEMENTOS Y SETS
# ======================================================

class ElementoSet(db.Model):
    __tablename__ = 'elemento_set'

    elemento_set_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)

    detalles = db.relationship("ElementoDetalle", back_populates="elemento_set")


class Elemento(db.Model):
    __tablename__ = 'elemento'

    elemento_id = db.Column(db.String, primary_key=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False)

    nombre = db.Column(db.String, nullable=False)
    material = db.Column(db.String)
    cantidad = db.Column(db.Float)
    estatus = db.Column(db.String)

    subarea = db.relationship("SubArea", back_populates="elementos")


class ElementoDetalle(db.Model):
    __tablename__ = 'elemento_detalle'

    elemento_set_id = db.Column(db.String, db.ForeignKey('elemento_set.elemento_set_id'), primary_key=True)
    elemento_id = db.Column(db.String, db.ForeignKey('elemento.elemento_id'), primary_key=True)
    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'))
    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'))

    elemento_set = db.relationship("ElementoSet", back_populates="detalles")
    elemento = db.relationship("Elemento")
    receta = db.relationship("Receta")
    kit = db.relationship("Kit")

# ======================================================
# 9. PERSONAL Y ASIGNACIÓN BASE
# ======================================================

class Personal(db.Model):
    __tablename__ = 'personal'

    personal_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String, nullable=False)

    asignaciones = db.relationship("AsignacionPersonal", back_populates="personal", cascade="all, delete")


class AsignacionPersonal(db.Model):
    __tablename__ = 'asignacion_personal'

    asignacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    personal_id = db.Column(db.String, db.ForeignKey('personal.personal_id'), nullable=False, index=True)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), nullable=False, index=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), nullable=False, index=True)
    nivel_limpieza_asignado = db.Column(db.String, nullable=False)  # “basica”, “media”, “profunda”

    personal = db.relationship("Personal", back_populates="asignaciones")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")


# ======================================================
# 10. LANZAMIENTO (SEMANA / DÍA / TAREAS)
# ======================================================

class LanzamientoSemana(db.Model):
    __tablename__ = 'lanzamiento_semana'

    semana_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String)
    fecha_inicio = db.Column(db.Date, nullable=False)  # lunes de la semana

    dias = db.relationship("LanzamientoDia", back_populates="semana", cascade="all, delete")


class LanzamientoDia(db.Model):
    __tablename__ = 'lanzamiento_dia'

    dia_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    semana_id = db.Column(db.Integer, db.ForeignKey('lanzamiento_semana.semana_id'), nullable=False, index=True)
    fecha = db.Column(db.Date, nullable=False, index=True)

    semana = db.relationship("LanzamientoSemana", back_populates="dias")
    tareas = db.relationship("LanzamientoTarea", back_populates="dia", cascade="all, delete")


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
# 11. PLANTILLAS SEMANALES
# ======================================================

class PlantillaSemanal(db.Model):
    __tablename__ = 'plantilla_semanal'

    plantilla_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String, unique=True, nullable=False)
    creada_en = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("PlantillaItem", back_populates="plantilla", cascade="all, delete")
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

