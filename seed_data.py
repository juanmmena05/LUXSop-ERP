# seed_data.py
from app import create_app
from app.models import (
    db,
    NivelLimpieza,
    Metodologia,
    MetodologiaPasos,
    Area,
    SubArea,
    SOP,
    Fraccion,
    FraccionDetalle,
    Kit,
    KitDetalle,
    Herramienta,
    Quimico, 
    RecetaDetalle, 
    Receta, 
    Elemento,
    ElementoDetalle,
    ElementoSet,
    Personal

)

# ======================================
# INICIALIZAR APP Y CONTEXTO
# ======================================
print("🧪 Iniciando script seed_data...")

app = create_app()

with app.app_context():
    print("✅ Contexto de aplicación iniciado correctamente")
    print("DB URI:", app.config.get("SQLALCHEMY_DATABASE_URI"))
    print("✅ Iniciando carga de datos de ejemplo...")

    # ======================================
    # LIMPIAR TABLAS BASE (opcional)
    # ======================================
    db.session.query(FraccionDetalle).delete()
    db.session.query(Fraccion).delete()
    db.session.query(SOP).delete()
    db.session.query(SubArea).delete()
    db.session.query(Area).delete()
    db.session.query(MetodologiaPasos).delete()
    db.session.query(Metodologia).delete()
    db.session.query(NivelLimpieza).delete()
    db.session.commit()

    # ======================================
    # NIVELES DE LIMPIEZA
    # ======================================
    niveles = [
        NivelLimpieza(nivel_limpieza_id=1, nombre="basica", factor_nivel=0.8),
        NivelLimpieza(nivel_limpieza_id=2, nombre="media", factor_nivel=1.0),
        NivelLimpieza(nivel_limpieza_id=3, nombre="profunda", factor_nivel=1.3),
    ]
    db.session.add_all(niveles)


    # ======================================================
    # PERSONAL BASE — DIRECCIÓN
    # ======================================================
    personal_list = [
    Personal(personal_id="L0036", nombre="Barco Maria del Socorro"),
    Personal(personal_id="L0082", nombre="Estrada Jasso Clemencia"),
    Personal(personal_id="L0212", nombre="Muñoz Ledo Ruvalcaba Dulce Maria"),
    ]
    db.session.add_all(personal_list)


    # ======================================
    # METODOLOGÍAS Y PASOS AREA: DIRECCION SUBAREA: OFICINA 01 
    # ======================================
    
    metodologias = [
    # 🗑 SACAR BASURA
    Metodologia(metodologia_id="M_BASURA_B", nivel_limpieza_id=1, nombre="Sacar basura (básico)", descripcion="Retirar las bolsas de basura de cada bote y reemplazar con nuevas. Asegurar cierre adecuado de bolsas."),
    Metodologia(metodologia_id="M_BASURA_M", nivel_limpieza_id=2, nombre="Sacar basura (intermedio)", descripcion="Retirar basura, limpiar el interior de los botes con paño húmedo y desinfectante neutro antes de colocar nuevas bolsas."),
    Metodologia(metodologia_id="M_BASURA_P", nivel_limpieza_id=3, nombre="Sacar basura (profundo)", descripcion="Retirar basura, lavar completamente los botes con agua y detergente, desinfectar y secar antes de colocar nuevas bolsas."),

    # 🪑 SACUDIR MUEBLES
    Metodologia(metodologia_id="M_MUEBLES_B", nivel_limpieza_id=1, nombre="Sacudir muebles (básico)", descripcion="Retirar polvo superficial con paño seco o plumero en escritorios, mesas y repisas."),
    Metodologia(metodologia_id="M_MUEBLES_M", nivel_limpieza_id=2, nombre="Sacudir muebles (intermedio)", descripcion="Limpiar con paño húmedo y solución neutra todas las superficies de los muebles. Secar con paño limpio."),
    Metodologia(metodologia_id="M_MUEBLES_P", nivel_limpieza_id=3, nombre="Sacudir muebles (profundo)", descripcion="Desmontar objetos de las superficies, limpiar y desinfectar con producto bactericida; revisar bordes y esquinas."),

    # 🚻 LAVAR BAÑO
    Metodologia(metodologia_id="M_BANO_B", nivel_limpieza_id=1, nombre="Lavar baño (básico)", descripcion="Limpiar lavamanos y superficies con desinfectante neutro, reponer papel y jabón."),
    Metodologia(metodologia_id="M_BANO_M", nivel_limpieza_id=2, nombre="Lavar baño (intermedio)", descripcion="Lavar lavamanos, taza y piso con detergente y desinfectante. Revisar espejos y dispensadores."),
    Metodologia(metodologia_id="M_BANO_P", nivel_limpieza_id=3, nombre="Lavar baño (profundo)", descripcion="Limpieza integral con cepillado de muros, sanitarios, drenajes y accesorios; desinfección completa con cloro diluido."),

    # 🪟 LIMPIEZA DE VIDRIOS
    Metodologia(metodologia_id="M_VIDRIOS_B", nivel_limpieza_id=1, nombre="Limpieza de vidrios (básico)", descripcion="Limpiar vidrios accesibles con trapo de microfibra y limpiavidrios, retirando huellas y manchas ligeras."),
    Metodologia(metodologia_id="M_VIDRIOS_M", nivel_limpieza_id=2, nombre="Limpieza de vidrios (intermedio)", descripcion="Limpieza completa con atomizador, esponja y secador; eliminar manchas y polvo del marco."),
    Metodologia(metodologia_id="M_VIDRIOS_P", nivel_limpieza_id=3, nombre="Limpieza de vidrios (profundo)", descripcion="Limpieza exterior e interior de cristales, marcos y rieles; aplicar desengrasante y paño seco para acabado sin residuos."),

    # 🧽 LIMPIEZA DE PISO
    Metodologia(metodologia_id="M_PISO_B", nivel_limpieza_id=1, nombre="Limpieza de piso (básico)", descripcion="Barrido general y trapeado húmedo con solución neutra."),
    Metodologia(metodologia_id="M_PISO_M", nivel_limpieza_id=2, nombre="Limpieza de piso (intermedio)", descripcion="Barrido, trapeado y desinfección de zonas de alto tránsito; enjuagar y secar."),
    Metodologia(metodologia_id="M_PISO_P", nivel_limpieza_id=3, nombre="Limpieza de piso (profundo)", descripcion="Limpieza intensiva con desengrasante o pulidora; enjuagar, secar y aplicar sellador si aplica."),

    # 🧹 BARRER TAPETES
    Metodologia(metodologia_id="M_TAPETE_B", nivel_limpieza_id=1, nombre="Barrer tapetes (básico)", descripcion="Sacar tapetes pequeños y sacudirlos al aire libre para retirar polvo superficial."),
    Metodologia(metodologia_id="M_TAPETE_M", nivel_limpieza_id=2, nombre="Barrer tapetes (intermedio)", descripcion="Aspirar tapetes completamente y limpiar bordes con cepillo suave."),
    Metodologia(metodologia_id="M_TAPETE_P", nivel_limpieza_id=3, nombre="Barrer tapetes (profundo)", descripcion="Lavar tapetes con agua y detergente, enjuagar y dejar secar completamente antes de recolocar."),
    ]

    db.session.add_all(metodologias)

    pasos = [
    # 🗑 SACAR BASURA
    MetodologiaPasos(metodologia_id="M_BASURA_B", orden=1, instruccion="Colocar guantes y revisar que los botes no estén rebosados."),
    MetodologiaPasos(metodologia_id="M_BASURA_B", orden=2, instruccion="Retirar las bolsas de basura y amarrarlas firmemente."),
    MetodologiaPasos(metodologia_id="M_BASURA_B", orden=3, instruccion="Colocar bolsa nueva y revisar que el bote quede limpio externamente."),
    
    MetodologiaPasos(metodologia_id="M_BASURA_M", orden=1, instruccion="Vaciar los botes de basura y desechar el contenido en el área de acopio."),
    MetodologiaPasos(metodologia_id="M_BASURA_M", orden=2, instruccion="Limpiar el interior y exterior del bote con paño húmedo y desinfectante neutro."),
    MetodologiaPasos(metodologia_id="M_BASURA_M", orden=3, instruccion="Colocar bolsa nueva asegurando su ajuste y reubicar el bote correctamente."),
    
    MetodologiaPasos(metodologia_id="M_BASURA_P", orden=1, instruccion="Retirar la basura, lavar el bote con agua y detergente."),
    MetodologiaPasos(metodologia_id="M_BASURA_P", orden=2, instruccion="Desinfectar completamente el bote con solución clorada y enjuagar."),
    MetodologiaPasos(metodologia_id="M_BASURA_P", orden=3, instruccion="Dejar secar al aire, revisar estado general y colocar bolsa nueva."),

    # 🪑 SACUDIR MUEBLES
    MetodologiaPasos(metodologia_id="M_MUEBLES_B", orden=1, instruccion="Retirar polvo superficial con plumero o paño seco."),
    MetodologiaPasos(metodologia_id="M_MUEBLES_B", orden=2, instruccion="Recolocar objetos personales sin alterar el orden."),
    MetodologiaPasos(metodologia_id="M_MUEBLES_B", orden=3, instruccion="Verificar que no queden residuos visibles."),
    
    MetodologiaPasos(metodologia_id="M_MUEBLES_M", orden=1, instruccion="Humedecer paño con solución neutra y limpiar todas las superficies."),
    MetodologiaPasos(metodologia_id="M_MUEBLES_M", orden=2, instruccion="Secar con paño limpio y revisar esquinas o bordes."),
    MetodologiaPasos(metodologia_id="M_MUEBLES_M", orden=3, instruccion="Organizar elementos nuevamente sin alterar documentos."),
    
    MetodologiaPasos(metodologia_id="M_MUEBLES_P", orden=1, instruccion="Despejar por completo la superficie del mueble."),
    MetodologiaPasos(metodologia_id="M_MUEBLES_P", orden=2, instruccion="Aplicar desinfectante bactericida con atomizador."),
    MetodologiaPasos(metodologia_id="M_MUEBLES_P", orden=3, instruccion="Frotar con paño microfibra y secar cuidadosamente."),
    MetodologiaPasos(metodologia_id="M_MUEBLES_P", orden=4, instruccion="Revisar bordes y esquinas; reinstalar objetos en su posición."),

    # 🚻 LAVAR BAÑO
    MetodologiaPasos(metodologia_id="M_BANO_B", orden=1, instruccion="Aplicar desinfectante neutro en lavamanos y superficies."),
    MetodologiaPasos(metodologia_id="M_BANO_B", orden=2, instruccion="Limpiar con esponja y enjuagar con agua limpia."),
    MetodologiaPasos(metodologia_id="M_BANO_B", orden=3, instruccion="Secar y reponer insumos de papel y jabón."),
    
    MetodologiaPasos(metodologia_id="M_BANO_M", orden=1, instruccion="Cepillar lavamanos, taza y piso con detergente."),
    MetodologiaPasos(metodologia_id="M_BANO_M", orden=2, instruccion="Enjuagar, aplicar desinfectante y dejar actuar por 2 minutos."),
    MetodologiaPasos(metodologia_id="M_BANO_M", orden=3, instruccion="Secar superficies y revisar espejos y dispensadores."),
    
    MetodologiaPasos(metodologia_id="M_BANO_P", orden=1, instruccion="Aplicar solución clorada en muros, lavamanos y sanitarios."),
    MetodologiaPasos(metodologia_id="M_BANO_P", orden=2, instruccion="Cepillar drenajes y accesorios metálicos."),
    MetodologiaPasos(metodologia_id="M_BANO_P", orden=3, instruccion="Enjuagar con abundante agua, secar y ventilar el área."),

    # 🪟 LIMPIEZA DE VIDRIOS
    MetodologiaPasos(metodologia_id="M_VIDRIOS_B", orden=1, instruccion="Pulverizar limpiavidrios en la superficie accesible."),
    MetodologiaPasos(metodologia_id="M_VIDRIOS_B", orden=2, instruccion="Limpiar con paño microfibra en movimientos circulares."),
    MetodologiaPasos(metodologia_id="M_VIDRIOS_B", orden=3, instruccion="Secar con paño limpio para evitar marcas."),
    
    MetodologiaPasos(metodologia_id="M_VIDRIOS_M", orden=1, instruccion="Limpiar vidrios con esponja y solución limpiadora."),
    MetodologiaPasos(metodologia_id="M_VIDRIOS_M", orden=2, instruccion="Usar secador de goma de arriba hacia abajo."),
    MetodologiaPasos(metodologia_id="M_VIDRIOS_M", orden=3, instruccion="Limpiar marcos y rieles con paño húmedo."),
    
    MetodologiaPasos(metodologia_id="M_VIDRIOS_P", orden=1, instruccion="Desmontar vidrios accesibles si es posible."),
    MetodologiaPasos(metodologia_id="M_VIDRIOS_P", orden=2, instruccion="Lavar cristales con solución desengrasante."),
    MetodologiaPasos(metodologia_id="M_VIDRIOS_P", orden=3, instruccion="Enjuagar con agua limpia y secar sin dejar residuos."),
    MetodologiaPasos(metodologia_id="M_VIDRIOS_P", orden=4, instruccion="Limpiar marcos y rieles con cepillo pequeño."),

    # 🧽 LIMPIEZA DE PISO
    MetodologiaPasos(metodologia_id="M_PISO_B", orden=1, instruccion="Barrer el área completamente."),
    MetodologiaPasos(metodologia_id="M_PISO_B", orden=2, instruccion="Trapear con solución neutra y escurrida."),
    MetodologiaPasos(metodologia_id="M_PISO_B", orden=3, instruccion="Dejar secar al aire o con paño seco."),
    
    MetodologiaPasos(metodologia_id="M_PISO_M", orden=1, instruccion="Barrer, aspirar y retirar residuos grandes."),
    MetodologiaPasos(metodologia_id="M_PISO_M", orden=2, instruccion="Aplicar desinfectante en áreas de tránsito alto."),
    MetodologiaPasos(metodologia_id="M_PISO_M", orden=3, instruccion="Trapeado cruzado y secado inmediato."),
    
    MetodologiaPasos(metodologia_id="M_PISO_P", orden=1, instruccion="Aplicar desengrasante o limpiador alcalino."),
    MetodologiaPasos(metodologia_id="M_PISO_P", orden=2, instruccion="Frotar con fibra o pulidora de piso."),
    MetodologiaPasos(metodologia_id="M_PISO_P", orden=3, instruccion="Enjuagar con agua limpia y retirar exceso."),
    MetodologiaPasos(metodologia_id="M_PISO_P", orden=4, instruccion="Secar y aplicar sellador protector si aplica."),

    # 🧹 BARRER TAPETES
    MetodologiaPasos(metodologia_id="M_TAPETE_B", orden=1, instruccion="Enrollar o retirar el tapete del área."),
    MetodologiaPasos(metodologia_id="M_TAPETE_B", orden=2, instruccion="Sacudirlo al aire libre para eliminar el polvo."),
    MetodologiaPasos(metodologia_id="M_TAPETE_B", orden=3, instruccion="Recolocarlo correctamente."),
    
    MetodologiaPasos(metodologia_id="M_TAPETE_M", orden=1, instruccion="Aspirar ambos lados del tapete cuidadosamente."),
    MetodologiaPasos(metodologia_id="M_TAPETE_M", orden=2, instruccion="Cepillar bordes y esquinas para eliminar residuos."),
    MetodologiaPasos(metodologia_id="M_TAPETE_M", orden=3, instruccion="Aplicar desodorante textil si es necesario."),
    
    MetodologiaPasos(metodologia_id="M_TAPETE_P", orden=1, instruccion="Lavar el tapete con agua y detergente suave."),
    MetodologiaPasos(metodologia_id="M_TAPETE_P", orden=2, instruccion="Enjuagar con agua limpia hasta eliminar residuos."),
    MetodologiaPasos(metodologia_id="M_TAPETE_P", orden=3, instruccion="Dejar secar completamente al aire libre."),
    ]

    db.session.add_all(pasos)

    # ======================================
    # ÁREA 1: ADMINISTRACION DIRECCION - OFICINA 01 - SALA JUNTAS 01 - OFICINA 02
    # ======================================
    area1 = Area(area_id="AD-DI", area_nombre="Direccion", tipo_area="Administracion", cantidad_subareas=3, orden_area=1)

    sub1 = SubArea(subarea_id="AD-DI-OF-01", area_id="AD-DI", subarea_nombre="Oficina 01", superficie_subarea=30, frecuencia=1, orden_subarea=1)
    sub2 = SubArea(subarea_id="AD-DI-SA-01", area_id="AD-DI", subarea_nombre="Sala Juntas 01", superficie_subarea=40, frecuencia=1, orden_subarea=2)
    sub3 = SubArea(subarea_id="AD-DI-OF-02", area_id="AD-DI", subarea_nombre="Oficina 02", superficie_subarea=30, frecuencia=1, orden_subarea=3)

    db.session.add_all([area1, sub1, sub2, sub3])

    sop1 = SOP(sop_id="SOP-AD-DI-OF-01", subarea_id="AD-DI-OF-01", sop_codigo="SOP-01", observacion_critica_sop="Cuidar Elementos Decoracion || Cuidar Insumos Completos en Bano")
    sop2 = SOP(sop_id="SOP-AD-DI-SA-01", subarea_id="AD-DI-SA-01", sop_codigo="SOP-02", observacion_critica_sop="Cuidar Elementos de Tecnologia || Cuidar Elementos Pizarron")
    sop3 = SOP(sop_id="SOP-AD-DI-OF-02", subarea_id="AD-DI-OF-02", sop_codigo="SOP-03", observacion_critica_sop="Cuidar Elementos Decoracion || Cuidar Elementos Zapatos")

    db.session.add_all([sop1, sop2, sop3])

    # 🧩 SOP Oficina 01
    fracciones_of1 = [
    Fraccion(fraccion_id="F_AD_DI_OF01_BASURA", sop_id="SOP-AD-DI-OF-01", fraccion_nombre="Retirar basura", descripcion="Recolectar y desechar bolsas de basura, reponer con nuevas.", unidad_medida="pzas", tiempo_base_min=1.00, tipo_formula="fijo", orden=1, nota_tecnica="Verificar que los botes estén secos antes de colocar la bolsa nueva."),
    Fraccion(fraccion_id="F_AD_DI_OF01_MUEBLES", sop_id="SOP-AD-DI-OF-01", fraccion_nombre="Sacudir muebles", descripcion="Retirar polvo de escritorios, archiveros y superficies.", unidad_medida="pzas", tiempo_base_min=1.00, tipo_formula="por_pieza", orden=2, nota_tecnica="Evitar el uso de líquidos directamente sobre superficies de madera."),
    Fraccion(fraccion_id="F_AD_DI_OF01_BANO", sop_id="SOP-AD-DI-OF-01", fraccion_nombre="Lavar baño", descripcion="Limpieza general y desinfección de sanitarios y lavamanos.", unidad_medida="pzas", tiempo_base_min=2.00, tipo_formula="por_pieza", orden=3, nota_tecnica="Revisar que no haya fugas en sanitarios o llaves."),
    Fraccion(fraccion_id="F_AD_DI_OF01_VIDRIOS", sop_id="SOP-AD-DI-OF-01", fraccion_nombre="Limpieza de vidrios", descripcion="Limpieza interior de ventanas y cristales.", unidad_medida="m²", tiempo_base_min=0.50, tipo_formula="por_m2", orden=4, nota_tecnica="Evitar limpiar bajo luz solar directa para evitar manchas."),
    Fraccion(fraccion_id="F_AD_DI_OF01_PISO", sop_id="SOP-AD-DI-OF-01", fraccion_nombre="Limpieza de piso", descripcion="Trapeado y mantenimiento de pisos interiores.", unidad_medida="m²", tiempo_base_min=0.50, tipo_formula="por_m2", orden=5, nota_tecnica="Verificar que el piso esté completamente seco antes de habilitar el tránsito."),
    Fraccion(fraccion_id="F_AD_DI_OF01_TAPETES", sop_id="SOP-AD-DI-OF-01", fraccion_nombre="Barrer tapetes", descripcion="Limpieza y aspirado de tapetes decorativos.", unidad_medida="m²", tiempo_base_min=1.00, tipo_formula="por_m2", orden=6, nota_tecnica="No usar productos líquidos en tapetes textiles."),
    ]
    db.session.add_all(fracciones_of1)
    
    # ==========================================
    # Detalles OF1 (actualizado con superficie_aplicable)
    # ==========================================
    detalles_of1 = [
    FraccionDetalle(fraccion_detalle_id="FD_OF01_BASURA_B", fraccion_id="F_AD_DI_OF01_BASURA", nivel_limpieza_id=1, metodologia_id="M_BASURA_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_BASURA_M", fraccion_id="F_AD_DI_OF01_BASURA", nivel_limpieza_id=2, metodologia_id="M_BASURA_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_BASURA_P", fraccion_id="F_AD_DI_OF01_BASURA", nivel_limpieza_id=3, metodologia_id="M_BASURA_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_MUEBLES_B", fraccion_id="F_AD_DI_OF01_MUEBLES", nivel_limpieza_id=1, metodologia_id="M_MUEBLES_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF01_MUEBLES"),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_MUEBLES_M", fraccion_id="F_AD_DI_OF01_MUEBLES", nivel_limpieza_id=2, metodologia_id="M_MUEBLES_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF01_MUEBLES"),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_MUEBLES_P", fraccion_id="F_AD_DI_OF01_MUEBLES", nivel_limpieza_id=3, metodologia_id="M_MUEBLES_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF01_MUEBLES"),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_BANO_B", fraccion_id="F_AD_DI_OF01_BANO", nivel_limpieza_id=1, metodologia_id="M_BANO_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF01_BANO"),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_BANO_M", fraccion_id="F_AD_DI_OF01_BANO", nivel_limpieza_id=2, metodologia_id="M_BANO_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF01_BANO"),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_BANO_P", fraccion_id="F_AD_DI_OF01_BANO", nivel_limpieza_id=3, metodologia_id="M_BANO_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF01_BANO"),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_VIDRIOS_B", fraccion_id="F_AD_DI_OF01_VIDRIOS", nivel_limpieza_id=1, metodologia_id="M_VIDRIOS_B", ajuste_factor=1.0, superficie_aplicable=8.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_VIDRIOS_M", fraccion_id="F_AD_DI_OF01_VIDRIOS", nivel_limpieza_id=2, metodologia_id="M_VIDRIOS_M", ajuste_factor=1.0, superficie_aplicable=8.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_VIDRIOS_P", fraccion_id="F_AD_DI_OF01_VIDRIOS", nivel_limpieza_id=3, metodologia_id="M_VIDRIOS_P", ajuste_factor=1.0, superficie_aplicable=8.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_PISO_B", fraccion_id="F_AD_DI_OF01_PISO", nivel_limpieza_id=1, metodologia_id="M_PISO_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_PISO_M", fraccion_id="F_AD_DI_OF01_PISO", nivel_limpieza_id=2, metodologia_id="M_PISO_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_PISO_P", fraccion_id="F_AD_DI_OF01_PISO", nivel_limpieza_id=3, metodologia_id="M_PISO_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_TAPETES_B", fraccion_id="F_AD_DI_OF01_TAPETES", nivel_limpieza_id=1, metodologia_id="M_TAPETE_B", ajuste_factor=1.0, superficie_aplicable=3.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None, tiempo_unitario_min=2.0),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_TAPETES_M", fraccion_id="F_AD_DI_OF01_TAPETES", nivel_limpieza_id=2, metodologia_id="M_TAPETE_M", ajuste_factor=1.0, superficie_aplicable=3.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None, tiempo_unitario_min=2.5),
    FraccionDetalle(fraccion_detalle_id="FD_OF01_TAPETES_P", fraccion_id="F_AD_DI_OF01_TAPETES", nivel_limpieza_id=3, metodologia_id="M_TAPETE_P", ajuste_factor=1.0, superficie_aplicable=3.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None, tiempo_unitario_min=6.0),
    ]
    db.session.add_all(detalles_of1)

 
    # ======================================================
    # FRACCIONES — SOP-AD-DI-SA-01 (Sala Juntas 01)
    # ======================================================
    fracciones_sa1 = [
    Fraccion(fraccion_id="F_AD_DI_SA01_BASURA", sop_id="SOP-AD-DI-SA-01", fraccion_nombre="Retirar basura", descripcion="Recolectar y reemplazar bolsas de basura en contenedores.", unidad_medida="pzas", tiempo_base_min=1.0, tipo_formula="fijo", orden=1, nota_tecnica="Asegurar que no queden residuos en el fondo del contenedor antes de colocar la bolsa nueva."),
    Fraccion(fraccion_id="F_AD_DI_SA01_VIDRIOS", sop_id="SOP-AD-DI-SA-01", fraccion_nombre="Limpieza de vidrios", descripcion="Limpieza interior y exterior de cristales de la sala de juntas.", unidad_medida="m²", tiempo_base_min=0.50, tipo_formula="por_m2", orden=2, nota_tecnica="Evitar limpiar bajo luz solar directa para prevenir marcas o manchas."),
    Fraccion(fraccion_id="F_AD_DI_SA01_PISO", sop_id="SOP-AD-DI-SA-01", fraccion_nombre="Limpieza de piso", descripcion="Trapeado y mantenimiento del piso de la sala.", unidad_medida="m²", tiempo_base_min=0.50, tipo_formula="por_m2", orden=3, nota_tecnica="Asegurar que el piso quede seco para evitar resbalones antes de reingresar al área."),
    Fraccion(fraccion_id="F_AD_DI_SA01_TAPETES", sop_id="SOP-AD-DI-SA-01", fraccion_nombre="Barrer tapetes", descripcion="Aspirar o sacudir tapetes de entrada o decorativos.", unidad_medida="pzas", tiempo_base_min=1.0, tipo_formula="por_m2", orden=4, nota_tecnica="No utilizar productos líquidos ni cepillos duros en tapetes de tela o con bordes decorativos."),
    ]
    db.session.add_all(fracciones_sa1)

    # ==========================================
    # Detalles SA1 (actualizado con superficie_aplicable)
    # ==========================================
    detalles_sa1 = [
    FraccionDetalle(fraccion_detalle_id="FD_SA01_BASURA_B", fraccion_id="F_AD_DI_SA01_BASURA", nivel_limpieza_id=1, metodologia_id="M_BASURA_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_BASURA_M", fraccion_id="F_AD_DI_SA01_BASURA", nivel_limpieza_id=2, metodologia_id="M_BASURA_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_BASURA_P", fraccion_id="F_AD_DI_SA01_BASURA", nivel_limpieza_id=3, metodologia_id="M_BASURA_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_VIDRIOS_B", fraccion_id="F_AD_DI_SA01_VIDRIOS", nivel_limpieza_id=1, metodologia_id="M_VIDRIOS_B", ajuste_factor=1.0, superficie_aplicable=10.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_VIDRIOS_M", fraccion_id="F_AD_DI_SA01_VIDRIOS", nivel_limpieza_id=2, metodologia_id="M_VIDRIOS_M", ajuste_factor=1.0, superficie_aplicable=10.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_VIDRIOS_P", fraccion_id="F_AD_DI_SA01_VIDRIOS", nivel_limpieza_id=3, metodologia_id="M_VIDRIOS_P", ajuste_factor=1.0, superficie_aplicable=10.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_PISO_B", fraccion_id="F_AD_DI_SA01_PISO", nivel_limpieza_id=1, metodologia_id="M_PISO_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_PISO_M", fraccion_id="F_AD_DI_SA01_PISO", nivel_limpieza_id=2, metodologia_id="M_PISO_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_PISO_P", fraccion_id="F_AD_DI_SA01_PISO", nivel_limpieza_id=3, metodologia_id="M_PISO_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_TAPETES_B", fraccion_id="F_AD_DI_SA01_TAPETES", nivel_limpieza_id=1, metodologia_id="M_TAPETE_B", ajuste_factor=1.0, superficie_aplicable=4.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_TAPETES_M", fraccion_id="F_AD_DI_SA01_TAPETES", nivel_limpieza_id=2, metodologia_id="M_TAPETE_M", ajuste_factor=1.0, superficie_aplicable=4.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_SA01_TAPETES_P", fraccion_id="F_AD_DI_SA01_TAPETES", nivel_limpieza_id=3, metodologia_id="M_TAPETE_P", ajuste_factor=1.0, superficie_aplicable=4.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None),
    ]
    db.session.add_all(detalles_sa1)


    # ======================================================
    # FRACCIONES — SOP-AD-DI-OF-02 (Oficina 02)
    # ======================================================
    fracciones_of2 = [
    Fraccion(fraccion_id="F_AD_DI_OF02_BASURA", sop_id="SOP-AD-DI-OF-02", fraccion_nombre="Retirar basura", descripcion="Recolectar, reemplazar bolsas y revisar contenedores de oficina.", unidad_medida="pzas", tiempo_base_min=1.0, tipo_formula="fijo", orden=1, nota_tecnica="No sobrecargar las bolsas y revisar que los botes estén limpios antes de colocar una nueva."),
    Fraccion(fraccion_id="F_AD_DI_OF02_MUEBLES", sop_id="SOP-AD-DI-OF-02", fraccion_nombre="Sacudir muebles", descripcion="Limpieza general de mobiliario, sillas y escritorios.", unidad_medida="pzas", tiempo_base_min=1.0, tipo_formula="por_pieza", orden=2, nota_tecnica="No aplicar producto directamente sobre madera o pantallas; usar paño humedecido."),
    Fraccion(fraccion_id="F_AD_DI_OF02_VIDRIOS", sop_id="SOP-AD-DI-OF-02", fraccion_nombre="Limpieza de vidrios", descripcion="Limpieza de ventanas interiores y divisiones de vidrio.", unidad_medida="m²", tiempo_base_min=0.50, tipo_formula="por_m2", orden=3, nota_tecnica="Limpia en sentido vertical y luego horizontal para asegurar acabado sin rayas."),
    Fraccion(fraccion_id="F_AD_DI_OF02_PISO", sop_id="SOP-AD-DI-OF-02", fraccion_nombre="Limpieza de piso", descripcion="Trapeado de piso con producto neutro y revisión de esquinas.", unidad_medida="m²", tiempo_base_min=0.50, tipo_formula="por_m2", orden=4, nota_tecnica="Evitar exceso de humedad cerca de escritorios o conexiones eléctricas."),
    Fraccion(fraccion_id="F_AD_DI_OF02_TAPETES", sop_id="SOP-AD-DI-OF-02", fraccion_nombre="Barrer tapetes", descripcion="Aspirado y sacudido de tapetes individuales.", unidad_medida="pzas", tiempo_base_min=1.0, tipo_formula="por_m2", orden=5, nota_tecnica="Revisar que los tapetes estén completamente secos antes de recolocarlos."),
    ]
    db.session.add_all(fracciones_of2)


    detalles_of2 = [
    FraccionDetalle(fraccion_detalle_id="FD_OF02_BASURA_B", fraccion_id="F_AD_DI_OF02_BASURA", nivel_limpieza_id=1, metodologia_id="M_BASURA_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_BASURA_M", fraccion_id="F_AD_DI_OF02_BASURA", nivel_limpieza_id=2, metodologia_id="M_BASURA_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_BASURA_P", fraccion_id="F_AD_DI_OF02_BASURA", nivel_limpieza_id=3, metodologia_id="M_BASURA_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_BASURA", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_MUEBLES_B", fraccion_id="F_AD_DI_OF02_MUEBLES", nivel_limpieza_id=1, metodologia_id="M_MUEBLES_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF02_MUEBLES"),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_MUEBLES_M", fraccion_id="F_AD_DI_OF02_MUEBLES", nivel_limpieza_id=2, metodologia_id="M_MUEBLES_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF02_MUEBLES"),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_MUEBLES_P", fraccion_id="F_AD_DI_OF02_MUEBLES", nivel_limpieza_id=3, metodologia_id="M_MUEBLES_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id=None, receta_id=None, elemento_set_id="ES_AD_DI_OF02_MUEBLES"),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_VIDRIOS_B", fraccion_id="F_AD_DI_OF02_VIDRIOS", nivel_limpieza_id=1, metodologia_id="M_VIDRIOS_B", ajuste_factor=1.0, superficie_aplicable=6.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_VIDRIOS_M", fraccion_id="F_AD_DI_OF02_VIDRIOS", nivel_limpieza_id=2, metodologia_id="M_VIDRIOS_M", ajuste_factor=1.0, superficie_aplicable=6.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_VIDRIOS_P", fraccion_id="F_AD_DI_OF02_VIDRIOS", nivel_limpieza_id=3, metodologia_id="M_VIDRIOS_P", ajuste_factor=1.0, superficie_aplicable=6.0, kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_PISO_B", fraccion_id="F_AD_DI_OF02_PISO", nivel_limpieza_id=1, metodologia_id="M_PISO_B", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_PISO_M", fraccion_id="F_AD_DI_OF02_PISO", nivel_limpieza_id=2, metodologia_id="M_PISO_M", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_PISO_P", fraccion_id="F_AD_DI_OF02_PISO", nivel_limpieza_id=3, metodologia_id="M_PISO_P", ajuste_factor=1.0, superficie_aplicable=None, kit_id="KIT_PISOS", receta_id="R_PISOS", elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_TAPETES_B", fraccion_id="F_AD_DI_OF02_TAPETES", nivel_limpieza_id=1, metodologia_id="M_TAPETE_B", ajuste_factor=1.0, superficie_aplicable=2.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_TAPETES_M", fraccion_id="F_AD_DI_OF02_TAPETES", nivel_limpieza_id=2, metodologia_id="M_TAPETE_M", ajuste_factor=1.0, superficie_aplicable=2.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None),
    FraccionDetalle(fraccion_detalle_id="FD_OF02_TAPETES_P", fraccion_id="F_AD_DI_OF02_TAPETES", nivel_limpieza_id=3, metodologia_id="M_TAPETE_P", ajuste_factor=1.0, superficie_aplicable=2.0, kit_id="KIT_TAPETES", receta_id=None, elemento_set_id=None),
    ]
    db.session.add_all(detalles_of2)
    
    # ======================================================
    # HERRAMIENTAS BASE
    # ======================================================

    herramientas = [
    Herramienta(herramienta_id="H_ATOMIZADOR", nombre="Atomizador manual 1L", descripcion="Atomizador de plástico con gatillo ajustable para soluciones desinfectantes.", estatus="activo"),
    Herramienta(herramienta_id="H_PANO_MICRO", nombre="Paño microfibra gris", descripcion="Paño de microfibra color gris, para limpieza de superficies delicadas.", estatus="activo"),
    Herramienta(herramienta_id="H_PANO_VERDE", nombre="Paño microfibra verde", descripcion="Paño de microfibra color verde, para áreas comunes o mobiliario.", estatus="activo"),
    Herramienta(herramienta_id="H_TRAPEADOR", nombre="Trapeador plano microfibra", descripcion="Trapeador plano con sistema de velcro y mango ergonómico.", estatus="activo"),
    Herramienta(herramienta_id="H_CUBETA", nombre="Cubeta 10L con exprimidor", descripcion="Cubeta de 10 litros con escurridor manual integrado.", estatus="activo"),
    Herramienta(herramienta_id="H_GUANTES", nombre="Guantes de látex", descripcion="Guantes desechables de látex o nitrilo para tareas de limpieza.", estatus="activo"),
    Herramienta(herramienta_id="H_ESCOBA", nombre="Escoba de cerdas suaves", descripcion="Escoba ergonómica para barrer tapetes y superficies lisas.", estatus="activo"),
    Herramienta(herramienta_id="H_RECOGEDOR", nombre="Recogedor con mango largo", descripcion="Recogedor para residuos sólidos, uso con escoba.", estatus="activo"),
    Herramienta(herramienta_id="H_FRANELA_CRISTALES", nombre="Franela para cristales", descripcion="Franela o toalla especial para secado sin rayas en cristales.", estatus="activo"),
    ]
    db.session.add_all(herramientas)


    # ======================================================
    # KITS DE LIMPIEZA
    # ======================================================

    kits = [
    Kit(kit_id="KIT_SANITARIOS", nombre="Kit de sanitarios"),
    Kit(kit_id="KIT_MUEBLES", nombre="Kit de muebles y superficies"),
    Kit(kit_id="KIT_PISOS", nombre="Kit de pisos interiores"),
    Kit(kit_id="KIT_CRISTALES", nombre="Kit de cristales y vidrios"),
    Kit(kit_id="KIT_TAPETES", nombre="Kit de tapetes y alfombras"),
    ]
    db.session.add_all(kits)


    # ======================================================
    # DETALLES DE CADA KIT
    # ======================================================

    kit_detalles = [
    # --- Kit de sanitarios ---
    KitDetalle(kit_id="KIT_SANITARIOS", herramienta_id="H_GUANTES", color="Azul", nota="Uso exclusivo para baños."),
    KitDetalle(kit_id="KIT_SANITARIOS", herramienta_id="H_TRAPEADOR", color="Azul", nota="Trapeador exclusivo de baños."),
    KitDetalle(kit_id="KIT_SANITARIOS", herramienta_id="H_CUBETA", color="Azul", nota="Cubeta con escurridor, área sanitaria."),

    # --- Kit de muebles ---
    KitDetalle(kit_id="KIT_MUEBLES", herramienta_id="H_PANO_VERDE", color="Verde", nota="Paño asignado a limpieza de escritorios y mobiliario."),
    KitDetalle(kit_id="KIT_MUEBLES", herramienta_id="H_ATOMIZADOR", color="Verde", nota="Uso con desinfectante neutro."),

    # --- Kit de pisos ---
    KitDetalle(kit_id="KIT_PISOS", herramienta_id="H_TRAPEADOR", color="Gris", nota="Trapeador multiuso para pisos de oficina."),
    KitDetalle(kit_id="KIT_PISOS", herramienta_id="H_CUBETA", color="Gris", nota="Cubeta general para trapeado."),
    KitDetalle(kit_id="KIT_PISOS", herramienta_id="H_GUANTES", color="Gris", nota="Protección básica para tareas de piso."),

    # --- Kit de cristales ---
    KitDetalle(kit_id="KIT_CRISTALES", herramienta_id="H_FRANELA_CRISTALES", color="Blanco", nota="Secado sin rayas."),
    KitDetalle(kit_id="KIT_CRISTALES", herramienta_id="H_ATOMIZADOR", color="Blanco", nota="Uso con limpiavidrios."),
    KitDetalle(kit_id="KIT_CRISTALES", herramienta_id="H_GUANTES", color="Blanco", nota="Protección básica, tareas delicadas."),

    # --- Kit de tapetes ---
    KitDetalle(kit_id="KIT_TAPETES", herramienta_id="H_ESCOBA", color="Negro", nota="Escoba asignada a tapetes."),
    KitDetalle(kit_id="KIT_TAPETES", herramienta_id="H_RECOGEDOR", color="Negro", nota="Complemento para barrer."),
    KitDetalle(kit_id="KIT_TAPETES", herramienta_id="H_GUANTES", color="Negro", nota="Uso exclusivo en exteriores o tapetes."),
    ]
    db.session.add_all(kit_detalles)

    # ======================================================
    # QUÍMICOS BASE
    # ======================================================

    quimicos = [
    Quimico(quimico_id="Q_DETERGENTE_NEUTRO", nombre="Detergente neutro", categoria="Limpieza general", presentacion="1L", unidad_base="ml"),
    Quimico(quimico_id="Q_DESINFECTANTE_MULTI", nombre="Desinfectante multisuperficies", categoria="Desinfección", presentacion="1L", unidad_base="ml"),
    Quimico(quimico_id="Q_LIMPIAVIDRIOS", nombre="Limpiavidrios con amonio", categoria="Cristales", presentacion="1L", unidad_base="ml"),
    Quimico(quimico_id="Q_DESINCRUSTANTE", nombre="Desincrustante ácido", categoria="Baños", presentacion="1L", unidad_base="ml"),
    Quimico(quimico_id="Q_DETERGENTE_PISOS", nombre="Limpiador de pisos neutro", categoria="Pisos", presentacion="5L", unidad_base="ml"),
    Quimico(quimico_id="Q_DESENGRASANTE", nombre="Desengrasante alcalino", categoria="Cocinas", presentacion="1L", unidad_base="ml"),
    Quimico(quimico_id="Q_AMONIO_CUAT", nombre="Amonio cuaternario", categoria="Desinfección avanzada", presentacion="1L", unidad_base="ml"),
    Quimico(quimico_id="Q_JABON_MANOS", nombre="Jabón líquido manos", categoria="Higiene", presentacion="1L", unidad_base="ml"),
    Quimico(quimico_id="Q_ALCOHOL_70", nombre="Alcohol al 70%", categoria="Desinfección", presentacion="1L", unidad_base="ml"),
    ]
    db.session.add_all(quimicos)


    # ======================================================
    # RECETAS (Combinaciones de productos)
    # ======================================================

    recetas = [
    Receta(receta_id="R_SUPERFICIES", nombre="Solución para superficies generales"),
    Receta(receta_id="R_PISOS", nombre="Solución neutra para pisos interiores"),
    Receta(receta_id="R_VIDRIOS", nombre="Solución limpiavidrios lista para uso"),
    Receta(receta_id="R_SANITARIOS", nombre="Desinfección de baños y lavabos"),
    Receta(receta_id="R_DESINFECCION", nombre="Desinfección de contacto diario"),
    Receta(receta_id="R_TAPETES", nombre="Aromatización y limpieza ligera de tapetes"),
    ]
    db.session.add_all(recetas)


    # ======================================================
    # DETALLES DE CADA RECETA
    # ======================================================

    receta_detalles = [
    # --- R_SUPERFICIES ---
    RecetaDetalle(receta_id="R_SUPERFICIES", quimico_id="Q_DETERGENTE_NEUTRO", dosis=30, unidad_dosis="ml/L", nota="Diluir en 1 litro de agua para limpieza básica."),
    RecetaDetalle(receta_id="R_SUPERFICIES", quimico_id="Q_DESINFECTANTE_MULTI", dosis=20, unidad_dosis="ml/L", nota="Agregar al mismo atomizador para desinfección ligera."),

    # --- R_PISOS ---
    RecetaDetalle(receta_id="R_PISOS", quimico_id="Q_DETERGENTE_PISOS", dosis=40, unidad_dosis="ml/L", nota="Diluir en cubeta con 10L de agua."),
    RecetaDetalle(receta_id="R_PISOS", quimico_id="Q_AMONIO_CUAT", dosis=10, unidad_dosis="ml/L", nota="Complementar para áreas de tránsito medio."),

    # --- R_VIDRIOS ---
    RecetaDetalle(receta_id="R_VIDRIOS", quimico_id="Q_LIMPIAVIDRIOS", dosis=100, unidad_dosis="ml/L", nota="Uso directo en atomizador, no requiere dilución."),
    RecetaDetalle(receta_id="R_VIDRIOS", quimico_id="Q_ALCOHOL_70", dosis=50, unidad_dosis="ml/L", nota="Acelera el secado sin residuos."),

    # --- R_SANITARIOS ---
    RecetaDetalle(receta_id="R_SANITARIOS", quimico_id="Q_DESINCRUSTANTE", dosis=50, unidad_dosis="ml/L", nota="Aplicar directamente en sanitarios y lavabos."),
    RecetaDetalle(receta_id="R_SANITARIOS", quimico_id="Q_DESINFECTANTE_MULTI", dosis=30, unidad_dosis="ml/L", nota="Refuerzo general para superficies no porosas."),

    # --- R_DESINFECCION ---
    RecetaDetalle(receta_id="R_DESINFECCION", quimico_id="Q_AMONIO_CUAT", dosis=25, unidad_dosis="ml/L", nota="Diluir en atomizador para rociar sobre superficies."),
    RecetaDetalle(receta_id="R_DESINFECCION", quimico_id="Q_ALCOHOL_70", dosis=25, unidad_dosis="ml/L", nota="Desinfección rápida entre usos."),

    # --- R_TAPETES ---
    RecetaDetalle(receta_id="R_TAPETES", quimico_id="Q_DETERGENTE_NEUTRO", dosis=20, unidad_dosis="ml/L", nota="Diluir en atomizador y aplicar sobre tapete."),
    RecetaDetalle(receta_id="R_TAPETES", quimico_id="Q_DESINFECTANTE_MULTI", dosis=10, unidad_dosis="ml/L", nota="Refuerzo desinfectante aromático."),
    ]
    db.session.add_all(receta_detalles)


    # ======================================================
    # OFICINA 01 — ELEMENTOS
    # ======================================================
    elementos_of1 = [
    # Muebles
    Elemento(elemento_id="E_AD_DI_OF01_SILLA_EJECUTIVA", subarea_id="AD-DI-OF-01", nombre="Silla ejecutiva", material="Piel y metal", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF01_SILLAS_VISITA", subarea_id="AD-DI-OF-01", nombre="Sillas de visita", material="Tela y metal", cantidad=2, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF01_MESA_REDONDA", subarea_id="AD-DI-OF-01", nombre="Mesa redonda", material="Madera", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF01_SILLAS_MESA", subarea_id="AD-DI-OF-01", nombre="Sillas mesa redonda", material="Madera", cantidad=4, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF01_ESCRITORIO", subarea_id="AD-DI-OF-01", nombre="Escritorio", material="Madera", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF01_ARCHIVERO", subarea_id="AD-DI-OF-01", nombre="Mueble archivero", material="Madera", cantidad=1, estatus="activo"),

    # Baño
    Elemento(elemento_id="E_AD_DI_OF01_TAZA", subarea_id="AD-DI-OF-01", nombre="Taza de baño", material="Porcelana", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF01_LAVAMANOS", subarea_id="AD-DI-OF-01", nombre="Lavamanos", material="Porcelana", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF01_ESPEJO", subarea_id="AD-DI-OF-01", nombre="Espejo", material="Cristal", cantidad=1, estatus="activo"),
    ]
    db.session.add_all(elementos_of1)


    # ======================================================
    # OFICINA 01 — ELEMENTO SETS
    # ======================================================
    sets_of1 = [
    ElementoSet(elemento_set_id="ES_AD_DI_OF01_MUEBLES", nombre="Set Muebles Oficina 01"),
    ElementoSet(elemento_set_id="ES_AD_DI_OF01_BANO", nombre="Set Baño Oficina 01"),
    ]
    db.session.add_all(sets_of1)


    # ======================================================
    # OFICINA 01 — ELEMENTO DETALLES
    # ======================================================
    detalles_of1 = [
    # --- Set Muebles ---
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_MUEBLES", elemento_id="E_AD_DI_OF01_SILLA_EJECUTIVA", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_MUEBLES", elemento_id="E_AD_DI_OF01_SILLAS_VISITA", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_MUEBLES", elemento_id="E_AD_DI_OF01_MESA_REDONDA", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_MUEBLES", elemento_id="E_AD_DI_OF01_SILLAS_MESA", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_MUEBLES", elemento_id="E_AD_DI_OF01_ESCRITORIO", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_MUEBLES", elemento_id="E_AD_DI_OF01_ARCHIVERO", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),

    # --- Set Baño ---
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_BANO", elemento_id="E_AD_DI_OF01_TAZA", kit_id="KIT_SANITARIOS", receta_id="R_SANITARIOS"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_BANO", elemento_id="E_AD_DI_OF01_LAVAMANOS", kit_id="KIT_SANITARIOS", receta_id="R_SANITARIOS"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF01_BANO", elemento_id="E_AD_DI_OF01_ESPEJO", kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS"),
    ]
    db.session.add_all(detalles_of1)


    # ======================================================
    # SALA DE JUNTAS — ELEMENTOS
    # ======================================================
    elementos_sa1 = [
    Elemento(elemento_id="E_AD_DI_SA01_MESA_REDONDA", subarea_id="AD-DI-SA-01", nombre="Mesa de vidrio", material="Cristal y metal", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_SA01_SILLAS", subarea_id="AD-DI-SA-01", nombre="Sillas tapizadas", material="Tela y metal", cantidad=6, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_SA01_MUEBLE_AUX", subarea_id="AD-DI-SA-01", nombre="Mueble auxiliar", material="Madera", cantidad=1, estatus="activo"),
    ]
    db.session.add_all(elementos_sa1)


    # ======================================================
    # SALA DE JUNTAS — ELEMENTO SETS
    # ======================================================
    sets_sa1 = [
    ElementoSet(elemento_set_id="ES_AD_DI_SA01_MUEBLES", nombre="Set Muebles Sala de Juntas 01"),
    ]
    db.session.add_all(sets_sa1)


    # ======================================================
    # SALA DE JUNTAS — ELEMENTO DETALLES
    # ======================================================
    detalles_sa1 = [
    ElementoDetalle(elemento_set_id="ES_AD_DI_SA01_MUEBLES", elemento_id="E_AD_DI_SA01_MESA_REDONDA", kit_id="KIT_CRISTALES", receta_id="R_VIDRIOS"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_SA01_MUEBLES", elemento_id="E_AD_DI_SA01_SILLAS", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_SA01_MUEBLES", elemento_id="E_AD_DI_SA01_MUEBLE_AUX", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ]
    db.session.add_all(detalles_sa1)

    # ======================================================
    # OFICINA 02 — ELEMENTOS
    # ======================================================
    elementos_of2 = [
    Elemento(elemento_id="E_AD_DI_OF02_SILLA_EJECUTIVA", subarea_id="AD-DI-OF-02", nombre="Silla ejecutiva", material="Piel y metal", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF02_SILLAS_VISITA", subarea_id="AD-DI-OF-02", nombre="Sillas de visita", material="Tela y metal", cantidad=2, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF02_ESCRITORIO", subarea_id="AD-DI-OF-02", nombre="Escritorio", material="Madera", cantidad=1, estatus="activo"),
    Elemento(elemento_id="E_AD_DI_OF02_ARCHIVERO", subarea_id="AD-DI-OF-02", nombre="Mueble archivero", material="Madera", cantidad=1, estatus="activo"),
    ]
    db.session.add_all(elementos_of2)


    # ======================================================
    # OFICINA 02 — ELEMENTO SETS
    # ======================================================
    sets_of2 = [
    ElementoSet(elemento_set_id="ES_AD_DI_OF02_MUEBLES", nombre="Set Muebles Oficina 02"),
    ]
    db.session.add_all(sets_of2)


    # ======================================================
    # OFICINA 02 — ELEMENTO DETALLES
    # ======================================================
    detalles_of2 = [
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF02_MUEBLES", elemento_id="E_AD_DI_OF02_SILLA_EJECUTIVA", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF02_MUEBLES", elemento_id="E_AD_DI_OF02_SILLAS_VISITA", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF02_MUEBLES", elemento_id="E_AD_DI_OF02_ESCRITORIO", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ElementoDetalle(elemento_set_id="ES_AD_DI_OF02_MUEBLES", elemento_id="E_AD_DI_OF02_ARCHIVERO", kit_id="KIT_MUEBLES", receta_id="R_SUPERFICIES"),
    ]
    db.session.add_all(detalles_of2)

   
    
    db.session.commit()
    print("🎉 Dataset completo insertado correctamente.")
