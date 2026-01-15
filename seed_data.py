# seed_data_v2.py
from app import create_app
from app.models import (
    db,
    # Core
    NivelLimpieza,
    Area,
    SubArea,
    SOP,
    Personal,

    # Universal catalogo
    Fraccion,
    Metodologia,
    MetodologiaBase,
    MetodologiaBasePaso,

    # SOP armado
    SopFraccion,
    SopFraccionDetalle,

    # Recursos
    Herramienta,
    Kit,
    KitDetalle,
    Quimico,
    Receta,
    RecetaDetalle,
    Consumo,

    # Elementos
    Elemento,
    ElementoSet,
    ElementoDetalle,
)

print("🧪 Iniciando script seed_data_v2...")

app = create_app()

with app.app_context():
    print("✅ Contexto iniciado")
    print("DB URI:", app.config.get("SQLALCHEMY_DATABASE_URI"))

    # ======================================================
    # 0) LIMPIEZA (orden importante por FK)
    # ======================================================
    # OJO: borra de hijas → padres
    db.session.query(ElementoDetalle).delete()
    db.session.query(ElementoSet).delete()
    db.session.query(Elemento).delete()

    db.session.query(RecetaDetalle).delete()
    db.session.query(Receta).delete()
    db.session.query(Quimico).delete()

    db.session.query(KitDetalle).delete()
    db.session.query(Kit).delete()
    db.session.query(Herramienta).delete()

    db.session.query(SopFraccionDetalle).delete()
    db.session.query(SopFraccion).delete()
    db.session.query(Consumo).delete()  

    db.session.query(MetodologiaBasePaso).delete()
    db.session.query(Metodologia).delete()
    db.session.query(MetodologiaBase).delete()


    db.session.query(Fraccion).delete()

    db.session.query(SOP).delete()
    db.session.query(SubArea).delete()
    db.session.query(Area).delete()

    # Personal lo puedes dejar si quieres, pero aquí lo reinserto igual
    db.session.query(Personal).delete()

    db.session.query(NivelLimpieza).delete()
    db.session.commit()

    # ======================================================
    # 1) NIVELES DE LIMPIEZA
    # ======================================================
    niveles = [
        NivelLimpieza(nivel_limpieza_id=1, nombre="basica"),
        NivelLimpieza(nivel_limpieza_id=2, nombre="media"),
        NivelLimpieza(nivel_limpieza_id=3, nombre="profundo"),
    ]
    db.session.add_all(niveles)

    # ======================================================
    # 2) PERSONAL (se queda igual)
    # ======================================================
    personal_list = [
        Personal(personal_id="L0036", nombre="Barco Maria del Socorro"),
        Personal(personal_id="L0082", nombre="Estrada Jasso Clemencia"),
        Personal(personal_id="L0212", nombre="Muñoz Ledo Ruvalcaba Dulce Maria"),
    ]
    db.session.add_all(personal_list)

    # ======================================================
    # 3) AREA + SUBAREAS (igual)
    # ======================================================
    area1 = Area(
        area_id="AD-DI",
        area_nombre="Direccion",
        division="Administracion",
        cantidad_subareas=4,
        orden_area=1
    )

    sub1 = SubArea(subarea_id="AD-DI-BA-001", area_id="AD-DI", subarea_nombre="Bano 001", superficie_subarea=10, frecuencia=1, orden_subarea=1)
    sub2 = SubArea(subarea_id="AD-DI-OF-001", area_id="AD-DI", subarea_nombre="Oficina 001", superficie_subarea=30, frecuencia=1, orden_subarea=2)
    sub3 = SubArea(subarea_id="AD-DI-SA-001", area_id="AD-DI", subarea_nombre="Sala Juntas 001", superficie_subarea=40, frecuencia=1, orden_subarea=3)
    sub4 = SubArea(subarea_id="AD-DI-OF-002", area_id="AD-DI", subarea_nombre="Oficina 002", superficie_subarea=30, frecuencia=1, orden_subarea=4)
    db.session.add_all([area1, sub1, sub2, sub3, sub4])

    # ======================================================
    # 4) SOP (nuevo formato: SP-<SUBAREA_ID>)
    # ======================================================
    sop1 = SOP(sop_id="SP-AD-DI-BA-001", subarea_id="AD-DI-BA-001", observacion_critica_sop="Cuidar decoración")
    sop2 = SOP(sop_id="SP-AD-DI-OF-001", subarea_id="AD-DI-OF-001", observacion_critica_sop="Cuidar decoración")
    sop3 = SOP(sop_id="SP-AD-DI-SA-001", subarea_id="AD-DI-SA-001", observacion_critica_sop="Cuidar decoración")
    sop4 = SOP(sop_id="SP-AD-DI-OF-002", subarea_id="AD-DI-OF-002", observacion_critica_sop="Cuidar decoración")
    db.session.add_all([sop1, sop2, sop3, sop4])

    # ======================================================
    # 5) FRACCIONES UNIVERSALES (catálogo)
    # ======================================================
    # Aquí NO van amarradas a SOP.

    fr_co_001 = Fraccion(fraccion_id="FR-SE-001", fraccion_nombre="Colocar Senaletica", nota_tecnica= "")
    fr_bs_001 = Fraccion(fraccion_id="FR-BS-001", fraccion_nombre="Sacar Basura", nota_tecnica="Si hay liquido en el bote, proceder a lavado extraordinario")
    fr_sp_001 = Fraccion(fraccion_id="FR-SP-001", fraccion_nombre="Sacudir Superficies", nota_tecnica="No sacudir superficies despues de la limpieza de pisos")
    fr_vi_001 = Fraccion(fraccion_id="FR-VI-001", fraccion_nombre="Limpiar Vidrios", nota_tecnica="")
    fr_ba_001 = Fraccion(fraccion_id="FR-BA-001", fraccion_nombre="Barrer", nota_tecnica="Aplicar presion media en zonas con exceso de polvo.")
    db.session.add_all([fr_co_001, fr_bs_001, fr_sp_001, fr_vi_001, fr_ba_001])

    # ======================================================
    # 6) METODOLOGÍAS (por fracción + nivel)
    # Formato: MT-<FRACCION>-<###>-<B|M|P>
    # ======================================================
    # ======================================================
# 6) METODOLOGÍAS (NUEVO ESQUEMA: BASE + ASIGNACIÓN)
# ======================================================

    metodologias_base = [
        # Colocar Señalética (misma para B/M/P)
        MetodologiaBase(
            metodologia_base_id="MB-SE-001",
            nombre="Colocar Señalética",
            descripcion="Colocar señalética en la entrada de la subárea"
        ),

        # Sacar Basura (B y M iguales -> compartimos base)
        MetodologiaBase(
            metodologia_base_id="MB-BS-001-BM",
            nombre="Sacar Basura (B/M)",
            descripcion="Retirar bolsas y reemplazar por nuevas."
        ),
        # Sacar Basura (P diferente)
        MetodologiaBase(
            metodologia_base_id="MB-BS-001-P",
            nombre="Sacar Basura (P)",
            descripcion="Retirar basura, sacudir bote, reemplazar bolsas"
        ),

        # Sacudir Superficies (solo P)
        MetodologiaBase(
            metodologia_base_id="MB-SP-001-P",
            nombre="Sacudir Superficies (P)",
            descripcion="Despejar, limpiar bordes y esquinas superiores."
        ),

        # Limpiar Vidrios (solo P)
        MetodologiaBase(
            metodologia_base_id="MB-VI-001-P",
            nombre="Limpiar Vidrios (P)",
            descripcion="Limpiar Vidrios"
        ),

        # Barrer (cada nivel distinto)
        MetodologiaBase(
            metodologia_base_id="MB-BA-001-B",
            nombre="Barrer (B)",
            descripcion="Barrer"
        ),
        MetodologiaBase(
            metodologia_base_id="MB-BA-001-M",
            nombre="Barrer (M)",
            descripcion="Barrer"
        ),
        MetodologiaBase(
            metodologia_base_id="MB-BA-001-P",
            nombre="Barrer (P)",
            descripcion="Barrer"
        ),
    ]
    db.session.add_all(metodologias_base)


    pasos_base = [
        # ===== Señalética (misma base para B/M/P) =====
        MetodologiaBasePaso(metodologia_base_id="MB-SE-001", orden=1, instruccion="Verifique si hay personas en el área y solicite autorización para iniciar la limpieza"),
        MetodologiaBasePaso(metodologia_base_id="MB-SE-001", orden=2, instruccion="Coloque la señal de “Área en limpieza / Piso mojado” en el acceso principal (visible desde la entrada)"),
        MetodologiaBasePaso(metodologia_base_id="MB-SE-001", orden=3, instruccion="Mantenga la puerta abierta durante toda la actividad de limpieza para asegurar ventilación y visibilidad del área"),
        MetodologiaBasePaso(metodologia_base_id="MB-SE-001", orden=4, instruccion="Retire la señal solo cuando el piso esté seco y sin riesgo"),

        # ===== Basura (B/M compartida) =====
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-BM", orden=1, instruccion="Retire la bolsa del bote, ciérrela con un nudo firme y deposítela en el contenedor asignado"),
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-BM", orden=2, instruccion="Verifique que el bote quede libre de residuos visibles por dentro"),
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-BM", orden=3, instruccion="Coloque una bolsa nueva del tamaño correcto y ajústela al borde"),

        # ===== Basura (P) =====
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-P", orden=1, instruccion="Retire la bolsa del bote, ciérrela con un nudo firme y deposítela en el contenedor asignado."),
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-P", orden=2, instruccion="Aplique químico al paño y use la técnica TM-SA-001 (8 caras)."),
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-P", orden=3, instruccion="Limpie el interior y exterior del bote, cambiando de cara conforme se ensucie."),
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-P", orden=4, instruccion="Use una cara seca para retirar humedad y dar acabado."),
        MetodologiaBasePaso(metodologia_base_id="MB-BS-001-P", orden=5, instruccion="Coloque una bolsa nueva del tamaño correcto y ajústela al borde."),

        # ===== Sacudir Superficies (P) =====
        MetodologiaBasePaso(metodologia_base_id="MB-SP-001-P", orden=1, instruccion="Verificar que la funda de microfibra esté limpia, seca y en buen estado."),
        MetodologiaBasePaso(metodologia_base_id="MB-SP-001-P", orden=2, instruccion="Colocar el plumero de forma que tenga contacto total con la superficie."),
        MetodologiaBasePaso(metodologia_base_id="MB-SP-001-P", orden=3, instruccion="Sacude la superficie con movimientos suaves y rectos: De arriba hacia abajo lineales y continuos, y de atrás hacia adelante, evitando movimientos rápidos o circulares que provoquen dispersión del polvo."),
        MetodologiaBasePaso(metodologia_base_id="MB-SP-001-P", orden=4, instruccion="Cambiar la funda de microfibra cuando este visiblemente sucia o llena de polvo."),

        # ===== Vidrios (P) =====
        MetodologiaBasePaso(metodologia_base_id="MB-VI-001-P", orden=1, instruccion="Vidrios altos: Aplique el químico uniformemente sobre el mop de vidrios (TM-VI-02) y ajuste bastón retractil de acuerdo a la altura requerida."),
        MetodologiaBasePaso(metodologia_base_id="MB-VI-001-P", orden=2, instruccion="Coloque el mop de vidrios en el área a limpiar, asegurando contacto completo con el vidrio, manteniendo presión ligera y uniforme."),
        MetodologiaBasePaso(metodologia_base_id="MB-VI-001-P", orden=3, instruccion="Comenzar a limpiar de arriba hacia abajo y de izquierda a derecha hasta cubrir completamente la superficie alcanzable."),
        MetodologiaBasePaso(metodologia_base_id="MB-VI-001-P", orden=4, instruccion="Vidrios medios e inferiores: Aplique el químico directamente sobre la microfibra y prepare el paño utilizando la técnica de 8 caras (TM-SA-001)."),
        MetodologiaBasePaso(metodologia_base_id="MB-VI-001-P", orden=5, instruccion="Limpie el vidrio de arriba hacia abajo y de izquierda a derecha utilizando la técnica (TM-VI-001) una cara húmeda de la microfibra; cambiar cara cuando esté sucia."),
        MetodologiaBasePaso(metodologia_base_id="MB-VI-001-P", orden=6, instruccion="Revise el vidrio contra la luz y corrija irregularidades utilizando la técnica de 8 caras (TM-SA-001)."),

        # ===== Barrer (B) =====
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-B", orden=1, instruccion="No mueva muebles ni objetos; solo se barrerán las áreas visibles."),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-B", orden=2, instruccion="Aplique Barrido Bajo (TM-BA-001): barridos cortos, lineales y con presión ligera"),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-B", orden=3, instruccion="Conduzca la basura hacia un solo montón de recolección por subárea y recójala con el recogedor, depositando en la bolsa o bote asignado."),

        # ===== Barrer (M) =====
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-M", orden=1, instruccion="Mueva únicamente objetos ligeros (botes, sillas, cestos, orillas de alfombras) para permitir el acceso al piso."),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-M", orden=2, instruccion="Aplique Barrido Medio (TM-BA-002): barridos cortos, lineales y con presión ligera."),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-M", orden=3, instruccion="Asegure el barrido de las orillas visibles y la zona por debajo de los objetos movidos."),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-M", orden=4, instruccion="Conduzca la basura hacia un solo montón de recolección por subárea y recójala con el recogedor, depositando en la bolsa o bote asignado."),

        # ===== Barrer (P) =====
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-P", orden=1, instruccion="Mueva todos los objetos posibles del área (solo los que pueda cargar con seguridad) para descubrir zonas ocultas del piso."),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-P", orden=2, instruccion="Aplique Barrido Profundo (TM-BA-003): barridos cortos, lineales, con presión ligera–media."),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-P", orden=3, instruccion="Asegure el barrido de orillas, bordes y esquinas, así como de todas las zonas ocultas expuestas."),
        MetodologiaBasePaso(metodologia_base_id="MB-BA-001-P", orden=4, instruccion="Conduzca la basura hacia un solo montón de recolección por subárea y recójala con el recogedor, depositando en la bolsa o bote asignado."),
    ]
    db.session.add_all(pasos_base)


    # ===== Asignaciones: (fraccion_id, nivel) -> metodologia_base =====
    asignaciones_met = [
        # Señalética: misma base para B/M/P
        Metodologia(fraccion_id="FR-SE-001", nivel_limpieza_id=1, metodologia_base_id="MB-SE-001"),
        Metodologia(fraccion_id="FR-SE-001", nivel_limpieza_id=2, metodologia_base_id="MB-SE-001"),
        Metodologia(fraccion_id="FR-SE-001", nivel_limpieza_id=3, metodologia_base_id="MB-SE-001"),

        # Basura: B/M comparten; P usa otra base
        Metodologia(fraccion_id="FR-BS-001", nivel_limpieza_id=1, metodologia_base_id="MB-BS-001-BM"),
        Metodologia(fraccion_id="FR-BS-001", nivel_limpieza_id=2, metodologia_base_id="MB-BS-001-BM"),
        Metodologia(fraccion_id="FR-BS-001", nivel_limpieza_id=3, metodologia_base_id="MB-BS-001-P"),

        # Superficies: solo P
        Metodologia(fraccion_id="FR-SP-001", nivel_limpieza_id=3, metodologia_base_id="MB-SP-001-P"),

        # Vidrios: solo P
        Metodologia(fraccion_id="FR-VI-001", nivel_limpieza_id=3, metodologia_base_id="MB-VI-001-P"),

        # Barrer: cada nivel diferente
        Metodologia(fraccion_id="FR-BA-001", nivel_limpieza_id=1, metodologia_base_id="MB-BA-001-B"),
        Metodologia(fraccion_id="FR-BA-001", nivel_limpieza_id=2, metodologia_base_id="MB-BA-001-M"),
        Metodologia(fraccion_id="FR-BA-001", nivel_limpieza_id=3, metodologia_base_id="MB-BA-001-P"),
    ]
    db.session.add_all(asignaciones_met)



    # ======================================================
    # 7) HERRAMIENTAS / KITS / QUÍMICOS / RECETAS (mínimo)
    # ======================================================
    herramientas = [
        Herramienta(herramienta_id="HE-SE-001", nombre="SEÑALETICA", descripcion="Señaletica Humedo", estatus="activo"),
        Herramienta(herramienta_id="HE-PA-001", nombre="PAÑO", descripcion="Paño Microfibra", estatus="activo"),
        Herramienta(herramienta_id="HE-BA-002", nombre="BASTON", descripcion="Bastón Retractil ", estatus="activo"),
        Herramienta(herramienta_id="HE-PL-001", nombre="PLUMERO", descripcion="Plumero Microfibra", estatus="activo"),
        Herramienta(herramienta_id="HE-PA-002", nombre="PAÑO", descripcion="Paño Vidrios", estatus="activo"),
        Herramienta(herramienta_id="HE-MO-002", nombre="MOP", descripcion="MOP Vidrios", estatus="activo"),
        Herramienta(herramienta_id="HE-ES-001", nombre="ESCOBA", descripcion="Escoba Angular", estatus="activo"),
        Herramienta(herramienta_id="HE-RE-001", nombre="RECOGEDOR", descripcion="Recogedor", estatus="activo"),
    ]
    db.session.add_all(herramientas)

    kits = [
        Kit(kit_id="KT-BS-001-P", nombre="Kit Basura"),
        Kit(kit_id="KT-SE-001", nombre="Kit Senaletica"),
        Kit(kit_id="KT-SP-001-P", nombre="Kit Superficie"),
        Kit(kit_id="KT-VI-001-P", nombre="Kit Vidrios Superior"),
        Kit(kit_id="KT-VI-002-P", nombre="Kit Vidrios Inferior"),
        Kit(kit_id="KT-BA-001", nombre="Kit Barrer"),
    ]
    db.session.add_all(kits)

    kit_detalles = [
        #Kit Senaletica
        KitDetalle(kit_id="KT-SE-001", herramienta_id="HE-SE-001", nota="Kit Senaletica"),

        #Kit Basura
        KitDetalle(kit_id="KT-BS-001-P", herramienta_id="HE-PA-001", nota="Kit Basura"),

        #Kit Superficie
        KitDetalle(kit_id="KT-SP-001-P", herramienta_id="HE-BA-002", nota="Kit Superficie"),
        KitDetalle(kit_id="KT-SP-001-P", herramienta_id="HE-PL-001", nota="Kit Superficie"),

        #Kit Vidrios Superior
        KitDetalle(kit_id="KT-VI-001-P", herramienta_id="HE-MO-002", nota="Kit Vidrios Superior"),
        KitDetalle(kit_id="KT-VI-001-P", herramienta_id="HE-BA-002", nota="Kit Vidrios Superior"),

        #Kit Vidrios Inferior
        KitDetalle(kit_id="KT-VI-002-P", herramienta_id="HE-PA-002", nota="Kit Vidrios Inferior"),

        #Kit Barrer
        KitDetalle(kit_id="KT-BA-001", herramienta_id="HE-ES-001", nota="Kit Barrer"),
        KitDetalle(kit_id="KT-BA-001", herramienta_id="HE-RE-001", nota="Kit Barrer"),
    
    ]
    db.session.add_all(kit_detalles)

    
    quimicos = [
        Quimico(quimico_id="QU-DS-001", nombre="Alpha HP", categoria="DESINFECTANTE", presentacion="Liquido", unidad_base="mL"),
        Quimico(quimico_id="QU-LI-001", nombre="Kristalux", categoria="LIMPIADOR", presentacion="Liquido", unidad_base="mL")
    ]
    db.session.add_all(quimicos)

    recetas = [
        Receta(receta_id="RE-SA-001", nombre="Sacudir Elementos"),
        Receta(receta_id="RE-VI-001", nombre="Limpiar Vidrios"),
    ]
    db.session.add_all(recetas)

    receta_detalles = [
        RecetaDetalle(receta_id="RE-SA-001", quimico_id="QU-DS-001", dosis=8, unidad_dosis="mL", volumen_base=1000, unidad_volumen="mL", nota="Sacudir Elementos"),
        RecetaDetalle(receta_id="RE-VI-001", quimico_id="QU-LI-001", dosis=50, unidad_dosis="mL", volumen_base=1000, unidad_volumen="mL", nota="Limpiar Vidrios"),
    ]
    db.session.add_all(receta_detalles)

    # ======================================================
    # 7.5) CONSUMO 
    # ======================================================
    consumo=[
        Consumo(consumo_id="CM-DS-003", valor=3, unidad="disparos", regla="= 3 mL"),
        Consumo(consumo_id="CM-DS-002", valor=2, unidad="disparos", regla="x 1m2 = 2 mL"),
        Consumo(consumo_id="CM-DS-001", valor=1, unidad="disparos", regla="x 1m2 = 1 mL")
    ]   
    

    db.session.add_all(consumo)


    # ======================================================
    # 8) ELEMENTOS (por subárea)
    # ======================================================
    elementos = [
        # AD-DI-BA-001
        Elemento(elemento_id="EL-IL-001", subarea_id="AD-DI-BA-001", nombre="ILLUXLÁMPARA", cantidad=1, estatus="activo", descripcion= "Iluxlampara" ),
        Elemento(elemento_id="EL-BO-001", subarea_id="AD-DI-BA-001", nombre="BORDE", cantidad=1, estatus="activo", descripcion= "Borde Pared" ),
        Elemento(elemento_id="EL-LM-001", subarea_id="AD-DI-BA-001", nombre="LAMPARA", cantidad=1, estatus="activo", descripcion= "Lampara Techo" ),
        Elemento(elemento_id="EL-BP-001", subarea_id="AD-DI-BA-001", nombre="BORDE", cantidad=1, estatus="activo", descripcion= "Borde Puerta" ),
        Elemento(elemento_id="EL-VI-001", subarea_id="AD-DI-BA-001", nombre="VIDRIO", cantidad=1, estatus="activo", descripcion= "Vidrio Superior" ),
        Elemento(elemento_id="EL-VI-002", subarea_id="AD-DI-BA-001", nombre="VIDRIO", cantidad=1, estatus="activo", descripcion= "Vidrio Inferior" ),
    ]
    db.session.add_all(elementos)

    # ======================================================
    # 9) ELEMENTO SET (por subárea + fracción + nivel)
    # Formato sugerido: ES-<SUBAREA>-<FRACCION>-<B|M|P>
    # ======================================================
    
    elementos_set = [
        ElementoSet( elemento_set_id="ES-SP-001-P",  subarea_id="AD-DI-BA-001", fraccion_id="FR-SP-001", nivel_limpieza_id=3, nombre="Elementos Superfcies"),
        ElementoSet( elemento_set_id="ES-VI-001-P",  subarea_id="AD-DI-BA-001", fraccion_id="FR-VI-001", nivel_limpieza_id=3, nombre="Elementos Vidrios")
    ]
    db.session.add_all(elementos_set)

    # ======================================================
    # 10) ELEMENTO DETALLE (cada elemento puede traer su kit/receta)
    # ======================================================
    elemento_detalles = [
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-IL-001", kit_id="KT-SP-001-P", receta_id=None, orden=2),
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-BO-001", kit_id="KT-SP-001-P", receta_id=None, orden=3),
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-LM-001", kit_id="KT-SP-001-P", receta_id=None, orden=1),
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-BP-001", kit_id="KT-SP-001-P", receta_id=None, orden=4),

        ElementoDetalle(elemento_set_id="ES-VI-001-P", elemento_id="EL-VI-001", kit_id="KT-VI-001-P", receta_id="RE-VI-001",consumo_id="CM-DS-002", orden=1),
        ElementoDetalle(elemento_set_id="ES-VI-001-P", elemento_id="EL-VI-002", kit_id="KT-VI-002-P", receta_id="RE-VI-001",consumo_id="CM-DS-001", orden=2),
    ]
    db.session.add_all(elemento_detalles)

    # ======================================================
    # 11) SOPFRACCION (qué fracciones tiene cada SOP)
    # Fracciones del SOP
    # ======================================================
    sf1 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-CO-001", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-SE-001", orden=1)
    sf2 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-BS-001", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-BS-001", orden=2)
    sf3 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-SP-001", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-SP-001", orden=3)
    sf4 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-VI-001", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-VI-001", orden=4)
    sf5 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-BA-001", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-BA-001", orden=5)


    db.session.add_all([sf1, sf2, sf3, sf4, sf5])

    # ======================================================
    # 12) SOPFRACCIONDETALLE (por nivel)
    # Formato: SD-<SOPFRACCION>-<NIVEL>
    # ======================================================
    detalles = [

        #Colocar Senaletica
        #   Bajo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-SE-001-B",
            sop_fraccion_id="SF-AD-DI-BA-001-SE-001",
            nivel_limpieza_id=1,
            kit_id="KT-SE-001",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=0.5
        ),

        #Colocar Senaletica
        #   Medio
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-SE-001-M",
            sop_fraccion_id="SF-AD-DI-BA-001-SE-001",
            nivel_limpieza_id=2,
            kit_id="KT-SE-001",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=0.5
        ),

        #Colocar Senaletica
        #   Profundo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-SE-001-P",
            sop_fraccion_id="SF-AD-DI-BA-001-SE-001",
            nivel_limpieza_id=3,
            kit_id="KT-SE-001",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=0.5
        ),

        
        #Sacar Basura
        #   Bajo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-BS-001-B",
            sop_fraccion_id="SF-AD-DI-BA-001-BS-001",
            nivel_limpieza_id=1,
            kit_id=None,
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=1
        ),

        #Sacar Basura
        #   Medio
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-BS-001-M",
            sop_fraccion_id="SF-AD-DI-BA-001-BS-001",
            nivel_limpieza_id=2,
            kit_id=None,
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=1
        ),

        #Sacar Basura
        #   Profundo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-BS-001-P",
            sop_fraccion_id="SF-AD-DI-BA-001-BS-001",
            nivel_limpieza_id=3,
            kit_id="KT-BS-001-P",
            receta_id="RE-SA-001",
            elemento_set_id=None,
            consumo_id="CM-DS-003",
            tiempo_unitario_min=5
        ),

        #Sacudir Superficies
        #   Profundo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-SP-001-P",
            sop_fraccion_id="SF-AD-DI-BA-001-SP-001",
            nivel_limpieza_id=3,
            kit_id=None,
            receta_id=None,
            elemento_set_id="ES-SP-001-P",
            tiempo_unitario_min=10
        ),

        #Limpiar Vidrios
        #   Profundo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-VI-001-P",
            sop_fraccion_id="SF-AD-DI-BA-001-VI-001",
            nivel_limpieza_id=3,
            kit_id=None,
            receta_id=None,
            elemento_set_id="ES-VI-001-P",
            tiempo_unitario_min=10
        ),

        #Barrer
        #   Bajo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-BA-001-B",
            sop_fraccion_id="SF-AD-DI-BA-001-BA-001",
            nivel_limpieza_id=1,
            kit_id="KT-BA-001",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=3
        ),

        #Barrer
        #   Medio
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-BA-001-M",
            sop_fraccion_id="SF-AD-DI-BA-001-BA-001",
            nivel_limpieza_id=2,
            kit_id="KT-BA-001",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=4
        ),

        #Barrer
        #   Medio
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-BA-001-P",
            sop_fraccion_id="SF-AD-DI-BA-001-BA-001",
            nivel_limpieza_id=3,
            kit_id="KT-BA-001",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=5
        ),
        
    ]
    db.session.add_all(detalles)

    db.session.commit()
    print("🎉 seed_data_v2 insertado correctamente.")
