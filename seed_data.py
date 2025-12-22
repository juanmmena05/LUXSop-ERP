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
    MetodologiaPasos,

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

    db.session.query(MetodologiaPasos).delete()
    db.session.query(Metodologia).delete()

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
        tipo_area="Administracion",
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

    fr_co_001 = Fraccion(fraccion_id= "FR-CO-001", fraccion_nombre="Colocar Senaletica", nota_tecnica= "")
    fr_bs_001 = Fraccion(fraccion_id="FR-BS-001", fraccion_nombre="Sacar Basura", nota_tecnica="Si hay liquido en el bote, proceder a lavado extraordinario")
    fr_sp_001 = Fraccion(fraccion_id="FR-SP-001", fraccion_nombre="Sacudir Superficies", nota_tecnica="No sacudir superficies despues de la limpieza de pisos")
    db.session.add_all([fr_co_001, fr_bs_001, fr_sp_001])

    # ======================================================
    # 6) METODOLOGÍAS (por fracción + nivel)
    # Formato: MT-<FRACCION>-<###>-<B|M|P>
    # ======================================================
    metodologias = [
        #Colocar Senaletica
        Metodologia(metodologia_id="MT-CO-001-B", fraccion_id="FR-CO-001", nivel_limpieza_id=1,
                    descripcion="Colocar senaletica en la entrada de la subarea"),
        Metodologia(metodologia_id="MT-CO-001-M", fraccion_id="FR-CO-001", nivel_limpieza_id=2,
                    descripcion="Colocar senaletica en la entrada de la subarea"),
        Metodologia(metodologia_id="MT-CO-001-P", fraccion_id="FR-CO-001", nivel_limpieza_id=3,
                    descripcion="Colocar senaletica en la entrada de la subarea"),
        
        
        # Sacar Basura
        Metodologia(metodologia_id="MT-BS-001-B", fraccion_id="FR-BS-001", nivel_limpieza_id=1,
                    descripcion="Retirar bolsas y reemplazar por nuevas."),
        Metodologia(metodologia_id="MT-BS-001-M", fraccion_id="FR-BS-001", nivel_limpieza_id=2,
                    descripcion="Retirar bolsas y reemplazar por nuevas."),
        Metodologia(metodologia_id="MT-BS-001-P", fraccion_id="FR-BS-001", nivel_limpieza_id=3,
                    descripcion="Retirar basura, sacudir bote, reemplazar bolsas"),

        # Sacudir Superficies
        # Solo existe la metodologia profunda para sacudir superficies
        Metodologia(metodologia_id="MT-SP-001-P", fraccion_id="FR-SP-001", nivel_limpieza_id=3,
                    descripcion="Despejar, limpiar y bordes y esquinas superiores."),
    ]
    db.session.add_all(metodologias)

    pasos = [
        #Colocar Senaletica
        #Baja
        MetodologiaPasos(metodologia_id="MT-CO-001-B", orden=1, instruccion="Verifique si hay personas en el área y solicite autorización para iniciar la limpieza"),
        MetodologiaPasos(metodologia_id="MT-CO-001-B", orden=2, instruccion="Coloque la señal de “Área en limpieza / Piso mojado” en el acceso principal (visible desde la entrada)"),
        MetodologiaPasos(metodologia_id="MT-CO-001-B", orden=3, instruccion="Mantenga la puerta abierta durante toda la actividad de limpieza para asegurar ventilación y visibilidad del área"),
        MetodologiaPasos(metodologia_id="MT-CO-001-B", orden=4, instruccion="Retire la señal solo cuando el piso esté seco y sin riesgo"),

        #Media
        MetodologiaPasos(metodologia_id="MT-CO-001-M", orden=1, instruccion="Verifique si hay personas en el área y solicite autorización para iniciar la limpieza"),
        MetodologiaPasos(metodologia_id="MT-CO-001-M", orden=2, instruccion="Coloque la señal de “Área en limpieza / Piso mojado” en el acceso principal (visible desde la entrada)"),
        MetodologiaPasos(metodologia_id="MT-CO-001-M", orden=3, instruccion="Mantenga la puerta abierta durante toda la actividad de limpieza para asegurar ventilación y visibilidad del área"),
        MetodologiaPasos(metodologia_id="MT-CO-001-M", orden=4, instruccion="Retire la señal solo cuando el piso esté seco y sin riesgo"),

        #Profunda
        MetodologiaPasos(metodologia_id="MT-CO-001-P", orden=1, instruccion="Verifique si hay personas en el área y solicite autorización para iniciar la limpieza"),
        MetodologiaPasos(metodologia_id="MT-CO-001-P", orden=2, instruccion="Coloque la señal de “Área en limpieza / Piso mojado” en el acceso principal (visible desde la entrada)"),
        MetodologiaPasos(metodologia_id="MT-CO-001-P", orden=3, instruccion="Mantenga la puerta abierta durante toda la actividad de limpieza para asegurar ventilación y visibilidad del área"),
        MetodologiaPasos(metodologia_id="MT-CO-001-P", orden=4, instruccion="Retire la señal solo cuando el piso esté seco y sin riesgo"),


        # Sacar Basura
        #Baja
        MetodologiaPasos(metodologia_id="MT-BS-001-B", orden=1, instruccion="Retire la bolsa del bote, ciérrela con un nudo firme y deposítela en el contenedor asignado"),
        MetodologiaPasos(metodologia_id="MT-BS-001-B", orden=2, instruccion="Verifique que el bote quede libre de residuos visibles por dentro"),
        MetodologiaPasos(metodologia_id="MT-BS-001-B", orden=3, instruccion="Coloque una bolsa nueva del tamaño correcto y ajústela al borde"),

        #Media
        MetodologiaPasos(metodologia_id="MT-BS-001-M", orden=1, instruccion="Retire la bolsa del bote, ciérrela con un nudo firme y deposítela en el contenedor asignado"),
        MetodologiaPasos(metodologia_id="MT-BS-001-M", orden=2, instruccion="Verifique que el bote quede libre de residuos visibles por dentro"),
        MetodologiaPasos(metodologia_id="MT-BS-001-M", orden=3, instruccion="Coloque una bolsa nueva del tamaño correcto y ajústela al borde"),

        #Profunda
        MetodologiaPasos(metodologia_id="MT-BS-001-P", orden=1, instruccion="Retire la bolsa del bote, ciérrela con un nudo firme y deposítela en el contenedor asignado."),
        MetodologiaPasos(metodologia_id="MT-BS-001-P", orden=2, instruccion="Aplique químico al paño y use la técnica TM-SA-001 (8 caras)."),
        MetodologiaPasos(metodologia_id="MT-BS-001-P", orden=3, instruccion="Limpie el interior y exterior del bote, cambiando de cara conforme se ensucie."),
        MetodologiaPasos(metodologia_id="MT-BS-001-P", orden=4, instruccion="Use una cara seca para retirar humedad y dar acabado."),
        MetodologiaPasos(metodologia_id="MT-BS-001-P", orden=5, instruccion="Coloque una bolsa nueva del tamaño correcto y ajústela al borde."),


        # Sacudir Superficies
        #Profunda
        MetodologiaPasos(metodologia_id="MT-SP-001-P", orden=1, instruccion="Verificar que la funda de microfibra esté limpia, seca y en buen estado."),
        MetodologiaPasos(metodologia_id="MT-SP-001-P", orden=2, instruccion="Colocar el plumero de forma que tenga contacto total con la superficie."),
        MetodologiaPasos(metodologia_id="MT-SP-001-P", orden=3, instruccion="Sacude la superficie con movimientos suaves y rectos: De arriba hacia abajo lineales y continuos, y de atrás hacia adelante, evitando movimientos rápidos o circulares que provoquen dispersión del polvo."),
        MetodologiaPasos(metodologia_id="MT-SP-001-P", orden=4, instruccion="ambiar la funda de microfibra cuando este visiblemente sucia o llena de polvo."),
        

    ]
    db.session.add_all(pasos)


    # ======================================================
    # 7) HERRAMIENTAS / KITS / QUÍMICOS / RECETAS (mínimo)
    # ======================================================
    herramientas = [
        Herramienta(herramienta_id="HE-SE-001", nombre="SEÑALETICA", descripcion="Señal de piso 2 caras", estatus="activo"),
        Herramienta(herramienta_id="HE-PA-001", nombre="PAÑO", descripcion="Paño de microfibra", estatus="activo"),
        Herramienta(herramienta_id="HE-BA-002", nombre="BASTON", descripcion="Bastón retractil", estatus="activo"),
        Herramienta(herramienta_id="HE-PL-001", nombre="PLUMERO", descripcion="Plumero de microfibra", estatus="activo"),
    ]
    db.session.add_all(herramientas)

    kits = [
        Kit(kit_id="KT-BS-001-P", nombre="Kit Basura"),
        Kit(kit_id="KT-CO-001-B", nombre="Kit Senaletica"),
        Kit(kit_id="KT-SP-001-P", nombre="Kit Superficie"),
    ]
    db.session.add_all(kits)

    kit_detalles = [
        #Kit Senaletica
        KitDetalle(kit_id="KT-CO-001-B", herramienta_id="HE-SE-001", nota="Kit Senaletica"),

        #Kit Basura
        KitDetalle(kit_id="KT-BS-001-P", herramienta_id="HE-PA-001", nota="Kit Basura"),

        #Kit Superficie
        KitDetalle(kit_id="KT-SP-001-P", herramienta_id="HE-BA-002", nota="Kit Superficie"),
        KitDetalle(kit_id="KT-SP-001-P", herramienta_id="HE-PL-001", nota="Kit Superficie"),
    ]
    db.session.add_all(kit_detalles)

    
    quimicos = [
        Quimico(quimico_id="QU-DS-001", nombre="Alpha HP", categoria="DESINFECTANTE", presentacion="Liquido", unidad_base="mL"),
    ]
    db.session.add_all(quimicos)

    recetas = [
        Receta(receta_id="RE-SA-001", nombre="Sacudir Elementos"),
    ]
    db.session.add_all(recetas)

    receta_detalles = [
        RecetaDetalle(receta_id="RE-SA-001", quimico_id="QU-DS-001", dosis=8, unidad_dosis="mL", volumen_base=1000, unidad_volumen="mL", nota="Sacudir Elementos"),
    ]
    db.session.add_all(receta_detalles)

    # ======================================================
    # 7.5) CONSUMO (solo aplica a Basura Profundo)
    # ======================================================
    cm_ds_003 = Consumo(
        consumo_id="CM-DS-003",
        valor=3,
        unidad="disparos",
        regla="= 3 mL"
    )
    db.session.add(cm_ds_003)



    # ======================================================
    # 8) ELEMENTOS (por subárea)
    # ======================================================
    elementos = [
        # AD-DI-BA-001
        Elemento(elemento_id="EL-IL-001", subarea_id="AD-DI-BA-001", nombre="ILLUXLÁMPARA", cantidad=1, estatus="activo"),
        Elemento(elemento_id="EL-BO-001", subarea_id="AD-DI-BA-001", nombre="BORDE", cantidad=1, estatus="activo"),
        Elemento(elemento_id="EL-LM-001", subarea_id="AD-DI-BA-001", nombre="LAMPARA", cantidad=1, estatus="activo"),
        Elemento(elemento_id="EL-BP-001", subarea_id="AD-DI-BA-001", nombre="BORDE", cantidad=1, estatus="activo"),
    ]
    db.session.add_all(elementos)

    # ======================================================
    # 9) ELEMENTO SET (por subárea + fracción + nivel)
    # Formato sugerido: ES-<SUBAREA>-<FRACCION>-<B|M|P>
    # ======================================================
    es_sp_001_p_ad_di_ba_001 = ElementoSet(
        elemento_set_id="ES-SP-001-P", 
        subarea_id="AD-DI-BA-001",
        fraccion_id="FR-SP-001",
        nivel_limpieza_id=3,
        nombre="Set Sacudir superficies AD-DI-BA-001 (Profunda)"
    )
    db.session.add_all([es_sp_001_p_ad_di_ba_001])

    # ======================================================
    # 10) ELEMENTO DETALLE (cada elemento puede traer su kit/receta)
    # ======================================================
    elemento_detalles = [
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-IL-001", kit_id="KT-SP-001-P", receta_id=None),
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-BO-001", kit_id="KT-SP-001-P", receta_id=None),
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-LM-001", kit_id="KT-SP-001-P", receta_id=None),
        ElementoDetalle(elemento_set_id="ES-SP-001-P", elemento_id="EL-BP-001", kit_id="KT-SP-001-P", receta_id=None),
    ]
    db.session.add_all(elemento_detalles)

    # ======================================================
    # 11) SOPFRACCION (qué fracciones tiene cada SOP)
    # Fracciones del SOP
    # ======================================================
    # BA-001: Senaletica + Basura + Sacudir Superficies
    sf1 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-1", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-CO-001", orden=1)
    sf2 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-2", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-BS-001", orden=2)
    sf3 = SopFraccion(sop_fraccion_id="SF-AD-DI-BA-001-3", sop_id="SP-AD-DI-BA-001", fraccion_id="FR-SP-001", orden=3)


    db.session.add_all([sf1, sf2, sf3])

    # ======================================================
    # 12) SOPFRACCIONDETALLE (por nivel)
    # Formato: SD-<SOPFRACCION>-<NIVEL>
    # ======================================================
    detalles = [

        #Colocar Senaletica
        #   Bajo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-1",
            sop_fraccion_id="SF-AD-DI-BA-001-1",
            nivel_limpieza_id=1,
            metodologia_id="MT-CO-001-B",
            kit_id="KT-CO-001-B",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=0.5
        ),

        #Colocar Senaletica
        #   Medio
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-2",
            sop_fraccion_id="SF-AD-DI-BA-001-1",
            nivel_limpieza_id=2,
            metodologia_id="MT-CO-001-M",
            kit_id="KT-CO-001-B",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=0.5
        ),

        #Colocar Senaletica
        #   Profundo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-3",
            sop_fraccion_id="SF-AD-DI-BA-001-1",
            nivel_limpieza_id=3,
            metodologia_id="MT-CO-001-P",
            kit_id="KT-CO-001-B",
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=0.5
        ),

        
        #Sacar Basura
        #   Bajo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-4",
            sop_fraccion_id="SF-AD-DI-BA-001-2",
            nivel_limpieza_id=1,
            metodologia_id="MT-BS-001-B",
            kit_id=None,
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=1
        ),

        #Sacar Basura
        #   Medio
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-5",
            sop_fraccion_id="SF-AD-DI-BA-001-2",
            nivel_limpieza_id=2,
            metodologia_id="MT-BS-001-M",
            kit_id=None,
            receta_id=None,
            elemento_set_id=None,
            tiempo_unitario_min=1
        ),

        #Sacar Basura
        #   Profundo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-6",
            sop_fraccion_id="SF-AD-DI-BA-001-2",
            nivel_limpieza_id=3,
            metodologia_id="MT-BS-001-P",
            kit_id="KT-BS-001-P",
            receta_id="RE-SA-001",
            elemento_set_id=None,
            consumo_id="CM-DS-003",
            tiempo_unitario_min=5
        ),

        #Sacudir Superficies
        #   Profundo
        SopFraccionDetalle(
            sop_fraccion_detalle_id="SD-AD-DI-BA-001-7",
            sop_fraccion_id="SF-AD-DI-BA-001-3",
            nivel_limpieza_id=3,
            metodologia_id="MT-SP-001-P",
            kit_id=None,
            receta_id=None,
            elemento_set_id="ES-SP-001-P",
            tiempo_unitario_min=10
        ),
        
    ]
    db.session.add_all(detalles)

    db.session.commit()
    print("🎉 seed_data_v2 insertado correctamente.")
