from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta



db = SQLAlchemy()

# ======================
# AREA
# ======================
class Area(db.Model):
    __tablename__ = 'area'

    area_id = db.Column(db.String, primary_key=True)

    area_nombre = db.Column(db.String)
    superficie_area = db.Column(db.Float)
    tipo_area = db.Column(db.String)
    cantidad_subareas = db.Column(db.Integer)
    tiempo_total_area = db.Column(db.Float)

    subareas = db.relationship("SubArea", back_populates="area")


# ======================
# SUBAREA
# ======================
class SubArea(db.Model):
    __tablename__ = 'sub_area'

    subarea_id = db.Column(db.String, primary_key=True)
    area_id = db.Column(db.String, db.ForeignKey('area.area_id'), index=True)

    subarea_nombre = db.Column(db.String)
    superficie_subarea = db.Column(db.Float)
    nivel_limpieza = db.Column(db.String)
    frecuencia = db.Column(db.Float)
    tiempo_total_subarea = db.Column(db.Float)

    # subarea N:1 area
    area = db.relationship("Area", back_populates="subareas")

    # subarea 1:N sop
    sops = db.relationship("SOP", back_populates="subarea")

    # subarea 1:N elemento
    elementos = db.relationship("Elemento", back_populates="subarea")


# ======================
# SOP
# ======================
class SOP(db.Model):
    __tablename__ = 'sop'

    sop_id = db.Column(db.String, primary_key=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), index=True)

    sop_codigo = db.Column(db.String)
    observacion_critica_sop = db.Column(db.String)

    # sop N:1 subarea
    subarea = db.relationship("SubArea", back_populates="sops")

    # sop 1:N fraccion
    fracciones = db.relationship("Fraccion", back_populates="sop")


# ======================
# METODOLOGIA
# ======================
class Metodologia(db.Model):
    __tablename__ = 'metodologia'

    metodologia_id = db.Column(db.String, primary_key=True)

    nombre = db.Column(db.String)
    descripcion = db.Column(db.Text)
    version = db.Column(db.String)
    estatus = db.Column(db.String)

    # metodologia 1:N metodologia_pasos
    pasos = db.relationship("MetodologiaPasos", back_populates="metodologia")

    # metodologia 1:N fraccion
    fracciones = db.relationship("Fraccion", back_populates="metodologia")


class MetodologiaPasos(db.Model):
    __tablename__ = 'metodologia_pasos'

    metodologia_id = db.Column(
        db.String,
        db.ForeignKey('metodologia.metodologia_id'),
        primary_key=True,
        index=True
    )
    orden = db.Column(db.Integer, primary_key=True)
    instruccion = db.Column(db.Text)

    # metodologia_pasos N:1 metodologia
    metodologia = db.relationship("Metodologia", back_populates="pasos")


# ======================
# FRACCION
# ======================
class Fraccion(db.Model):
    __tablename__ = 'fraccion'

    fraccion_id = db.Column(db.String, primary_key=True)
    sop_id = db.Column(db.String, db.ForeignKey('sop.sop_id'), index=True)
    metodologia_id = db.Column(db.String, db.ForeignKey('metodologia.metodologia_id'), index=True)
    
    orden = db.Column(db.Integer)
    fraccion_nombre = db.Column(db.String)
    descripcion = db.Column(db.Text)
    frecuencia_programada = db.Column(db.Float)
    frecuencia_condicional = db.Column(db.String)
    tiempo_fraccion = db.Column(db.Float)
    nivel_limpieza = db.Column(db.String)
    observacion_critica = db.Column(db.Text)

    # fraccion N:1 sop
    sop = db.relationship("SOP", back_populates="fracciones")

    # fraccion N:1 metodologia
    metodologia = db.relationship("Metodologia", back_populates="fracciones")

    # fraccion 1:N fraccion_detalle
    detalles = db.relationship("FraccionDetalle", back_populates="fraccion")


# ======================
# FRACCION DETALLE
# ======================
class FraccionDetalle(db.Model):
    __tablename__ = 'fraccion_detalle'

    fraccion_detalle_id = db.Column(db.String, primary_key=True)
    fraccion_id = db.Column(db.String, db.ForeignKey('fraccion.fraccion_id'), index=True)
    elemento_set_id = db.Column(db.String, db.ForeignKey('elemento_set.elemento_set_id'), index=True)
    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'), index=True)
    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'), index=True)

    # fraccion_detalle N:1 fraccion
    fraccion = db.relationship("Fraccion", back_populates="detalles")

    # fraccion_detalle N:1 elemento_set
    elemento_set = db.relationship("ElementoSet")

    # fraccion_detalle N:1 receta
    receta = db.relationship("Receta", back_populates="fraccion_detalles")

    # fraccion_detalle N:1 kit
    kit = db.relationship("Kit", back_populates="fraccion_detalles")


# ======================
# HERRAMIENTA
# ======================
class Herramienta(db.Model):
    __tablename__ = 'herramienta'

    herramienta_id = db.Column(db.String, primary_key=True)

    nombre = db.Column(db.String)
    descripcion = db.Column(db.Text)
    estatus = db.Column(db.String)

    # herramienta 1:N kit_detalle (desde el punto de vista herramienta)
    kit_detalles = db.relationship("KitDetalle", back_populates="herramienta")


# ======================
# KIT
# ======================
class Kit(db.Model):
    __tablename__ = 'kit'

    kit_id = db.Column(db.String, primary_key=True)

    nombre = db.Column(db.String)

    # kit 1:N kit_detalle
    detalles = db.relationship("KitDetalle", back_populates="kit")

    # kit 1:N fraccion_detalle
    fraccion_detalles = db.relationship("FraccionDetalle", back_populates="kit")

    # kit 1:N elemento_detalle
    elemento_detalles = db.relationship("ElementoDetalle", back_populates="kit")


class KitDetalle(db.Model):
    __tablename__ = 'kit_detalle'

    kit_id = db.Column(
        db.String,
        db.ForeignKey('kit.kit_id'),
        primary_key=True,
        index=True
    )

    herramienta_id = db.Column(
        db.String,
        db.ForeignKey('herramienta.herramienta_id'),
        primary_key=True,
        index=True
    )

    area_id = db.Column(db.String)      # opcional: db.ForeignKey('area.area_id')
    subarea_id = db.Column(db.String)   # opcional: db.ForeignKey('sub_area.subarea_id')

    color = db.Column(db.String)
    cantidad = db.Column(db.Float)
    nota = db.Column(db.String)

    # kit_detalle N:1 kit
    kit = db.relationship("Kit", back_populates="detalles")

    # kit_detalle N:1 herramienta
    herramienta = db.relationship("Herramienta", back_populates="kit_detalles")


# ======================
# RECETA / RECETA DETALLE / QUIMICO
# ======================
class Receta(db.Model):
    __tablename__ = 'receta'

    receta_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String)

    # receta 1:N receta_detalle
    detalles = db.relationship("RecetaDetalle", back_populates="receta")

    # receta 1:N fraccion_detalle
    fraccion_detalles = db.relationship("FraccionDetalle", back_populates="receta")

    # receta 1:N elemento_detalle
    elemento_detalles = db.relationship("ElementoDetalle", back_populates="receta")



class RecetaDetalle(db.Model):
    __tablename__ = 'receta_detalle'

    receta_id = db.Column(
        db.String,
        db.ForeignKey('receta.receta_id'),
        primary_key=True,
        index=True
    )

    quimico_id = db.Column(
        db.String,
        db.ForeignKey('quimico.quimico_id'),
        primary_key=True,
        index=True
    )

    dosis = db.Column(db.Float)
    unidad_dosis = db.Column(db.String)
    nota = db.Column(db.String)

    # receta_detalle N:1 receta
    receta = db.relationship("Receta", back_populates="detalles")

    # receta_detalle N:1 quimico
    quimico = db.relationship("Quimico", back_populates="recetas_detalle")


class Quimico(db.Model):
    __tablename__ = 'quimico'

    quimico_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String)
    categoria = db.Column(db.String)
    presentacion = db.Column(db.String)
    unidad_base = db.Column(db.String)

    # quimico 1:N receta_detalle
    recetas_detalle = db.relationship("RecetaDetalle", back_populates="quimico")


# ======================
# ELEMENTO SET / ELEMENTO DETALLE / ELEMENTO
# ======================
class ElementoSet(db.Model):
    __tablename__ = 'elemento_set'

    elemento_set_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String)

    # elemento_set 1:N elemento_detalle
    detalles = db.relationship("ElementoDetalle", back_populates="elemento_set")


class ElementoDetalle(db.Model):
    __tablename__ = 'elemento_detalle'

    elemento_set_id = db.Column(
        db.String,
        db.ForeignKey('elemento_set.elemento_set_id'),
        primary_key=True,
        index=True
    )

    elemento_id = db.Column(
        db.String,
        db.ForeignKey('elemento.elemento_id'),
        primary_key=True,
        index=True
    )

    receta_id = db.Column(db.String, db.ForeignKey('receta.receta_id'), index=True)
    kit_id = db.Column(db.String, db.ForeignKey('kit.kit_id'), index=True)
    
    # elemento_detalle N:1 elemento_set
    elemento_set = db.relationship("ElementoSet", back_populates="detalles")

    # elemento_detalle N:1 elemento
    elemento = db.relationship("Elemento")

    # elemento_detalle N:1 receta
    receta = db.relationship("Receta", back_populates="elemento_detalles")

    # elemento_detalle N:1 kit
    kit = db.relationship("Kit", back_populates="elemento_detalles")


class Elemento(db.Model):
    __tablename__ = 'elemento'

    elemento_id = db.Column(db.String, primary_key=True)
    subarea_id = db.Column(db.String, db.ForeignKey('sub_area.subarea_id'), index=True)

    nombre = db.Column(db.String)
    material = db.Column(db.String)
    cantidad = db.Column(db.Float)
    estatus = db.Column(db.String)

    # elemento N:1 subarea
    subarea = db.relationship("SubArea", back_populates="elementos")


# ======================
# PERSONAL / ASIGNACION_PERSONAL
# ======================
class Personal(db.Model):
    __tablename__ = 'personal'

    personal_id = db.Column(db.String, primary_key=True)
    nombre = db.Column(db.String)

    # PERSONAL 1:N ASIGNACION_PERSONAL
    asignaciones = db.relationship(
        "AsignacionPersonal",
        back_populates="personal",
        cascade="all, delete"
    )


class AsignacionPersonal(db.Model):
    __tablename__ = 'asignacion_personal'

    asignacion_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    personal_id = db.Column(
        db.String,
        db.ForeignKey('personal.personal_id'),
        index=True
    )

    area_id = db.Column(
        db.String,
        db.ForeignKey('area.area_id'),
        index=True
    )

    subarea_id = db.Column(
        db.String,
        db.ForeignKey('sub_area.subarea_id'),
        index=True
    )

    # nivel de limpieza que ESA persona debe ejecutar en ESA subárea
    nivel_limpieza_asignado = db.Column(db.String)

    # Relaciones ORM (todas N:1 hacia tablas maestras)
    personal = db.relationship(
        "Personal",
        back_populates="asignaciones"
    )

    area = db.relationship(
        "Area",
        lazy="joined"
    )

    subarea = db.relationship(
        "SubArea",
        lazy="joined"
    )


# ======================
# LANZAMINETO_SEMANA / LANZAMINETO_DIA / LANZAMINETO_TAREA
# ======================
from datetime import date

class LanzamientoSemana(db.Model):
    __tablename__ = 'lanzamiento_semana'

    semana_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Ejemplo: "Semana 03 Nov 2025"
    nombre = db.Column(db.String)

    # Lunes (o fecha base) de esa semana
    fecha_inicio = db.Column(db.Date)

    # Relación 1:N con los días de esa semana
    dias = db.relationship(
        "LanzamientoDia",
        back_populates="semana",
        cascade="all, delete"
    )


class LanzamientoDia(db.Model):
    __tablename__ = 'lanzamiento_dia'

    dia_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # A qué semana pertenece este día
    semana_id = db.Column(
        db.Integer,
        db.ForeignKey('lanzamiento_semana.semana_id'),
        index=True
    )

    # Fecha específica (ej. 2025-11-03)
    fecha = db.Column(db.Date, index=True)

    semana = db.relationship(
        "LanzamientoSemana",
        back_populates="dias"
    )

    # Relación 1:N con las tareas asignadas ese día
    tareas = db.relationship(
        "LanzamientoTarea",
        back_populates="dia",
        cascade="all, delete"
    )


class LanzamientoTarea(db.Model):
    __tablename__ = 'lanzamiento_tarea'

    tarea_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Este trabajo pertenece a qué día planificado
    dia_id = db.Column(
        db.Integer,
        db.ForeignKey('lanzamiento_dia.dia_id'),
        index=True
    )

    # Quién lo hace
    personal_id = db.Column(
        db.String,
        db.ForeignKey('personal.personal_id'),
        index=True
    )

    # Dónde lo hace (área grande)
    area_id = db.Column(
        db.String,
        db.ForeignKey('area.area_id'),
        index=True
    )

    # Dónde exactamente (subárea específica)
    subarea_id = db.Column(
        db.String,
        db.ForeignKey('sub_area.subarea_id'),
        index=True
    )

    # Qué nivel debe ejecutar esa persona en esa subárea ese día
    # Ej: "basica", "media", "profunda"
    nivel_limpieza_asignado = db.Column(db.String)

    # Relaciones ORM
    dia = db.relationship(
        "LanzamientoDia",
        back_populates="tareas"
    )

    personal = db.relationship("Personal", lazy="joined")
    area = db.relationship("Area", lazy="joined")
    subarea = db.relationship("SubArea", lazy="joined")



# ====================================
# PLANTILLA SEMANAL / ITEM / APLICADA
# ====================================
class PlantillaSemanal(db.Model):
    __tablename__ = 'plantilla_semanal'
    plantilla_id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), unique=True, nullable=False)
    creada_en = db.Column(db.DateTime, default=datetime.utcnow)


class PlantillaItem(db.Model):
    __tablename__ = 'plantilla_item'
    item_id = db.Column(db.Integer, primary_key=True)
    plantilla_id = db.Column(db.Integer, db.ForeignKey('plantilla_semanal.plantilla_id'), nullable=False)
    # 0 = Lunes ... 5 = Sábado (coincide con tus vistas)
    dia_index = db.Column(db.Integer, nullable=False)
    personal_id = db.Column(db.String(50), db.ForeignKey('personal.personal_id'), nullable=False)
    area_id = db.Column(db.String(50), db.ForeignKey('area.area_id'), nullable=False)
    subarea_id = db.Column(db.String(50), db.ForeignKey('sub_area.subarea_id'), nullable=False)
    nivel_limpieza_asignado = db.Column(db.String(20), nullable=False)

    plantilla = db.relationship('PlantillaSemanal', backref='items')


class PlantillaSemanaAplicada(db.Model):
    __tablename__ = 'plantilla_semana_aplicada'
    # Clave: el lunes de la semana (único)
    semana_lunes = db.Column(db.Date, primary_key=True)
    # Plantilla activa (nullable). Si es NULL, significa “Ninguna”.
    plantilla_id = db.Column(db.Integer, db.ForeignKey('plantilla_semanal.plantilla_id'), nullable=True)
    aplicada_en = db.Column(db.DateTime, default=datetime.utcnow)

    plantilla = db.relationship('PlantillaSemanal', backref='semanas_aplicadas')