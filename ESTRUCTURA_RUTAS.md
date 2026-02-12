# Estructura de Rutas y Templates - LuxSOP

## Resumen

| Blueprint | Archivo | Rutas | Descripción |
|-----------|---------|-------|-------------|
| auth | auth.py | 2 | Login, logout |
| home | home.py | 2 | Home, admin panel |
| rutas | rutas_bp.py | 9 | Mi ruta, plan día, asignaciones |
| reportes | reportes_bp.py | 2 | Reportes HTML y PDF |
| plantillas | plantillas_bp.py | 10 | Gestión de plantillas |
| sop | sop_bp.py | 8 | SOP regular, consecuente, evento |
| catalogos | catalogos_bp.py | 10 | Páginas HTML de catálogos |
| api | api_bp.py | 63 | APIs REST |

**Total: 106 rutas**

---

## Rutas por Blueprint

### auth (auth.py)
| Método | Ruta | Función | Descripción |
|--------|------|---------|-------------|
| GET,POST | `/login` | login | Página de inicio de sesión |
| POST | `/logout` | logout | Cerrar sesión |

### home (home.py)
| Método | Ruta | Función | Descripción |
|--------|------|---------|-------------|
| GET | `/` | home | Página principal con calendario |
| GET | `/admin` | home_admin_panel | Panel de administración |

### rutas (rutas_bp.py)
| Método | Ruta | Función | Descripción |
|--------|------|---------|-------------|
| GET | `/mi_ruta` | mi_ruta | Ruta del día para el usuario actual |
| GET | `/plan/<fecha>/ruta` | ruta_dia | Ver ruta de un día específico |
| GET,POST | `/plan/<fecha>/asignar` | plan_dia_asignar | Asignar tareas a un día |
| POST | `/plan/<fecha>/borrar/<tarea_id>` | borrar_tarea | Eliminar una tarea |
| GET,POST | `/personal/<personal_id>/asignar` | asignar_ruta | Asignar ruta a personal |
| GET | `/subareas_por_area/<area_id>` | subareas_por_area | Obtener subáreas de un área |
| GET | `/subareas_por_area_simple/<area_id>` | subareas_por_area_simple | Subáreas simplificadas |
| POST | `/api/reordenar-tareas` | reordenar_tareas | Reordenar tareas del día |
| POST | `/api/reordenar-plantilla-items` | reordenar_plantilla_items | Reordenar items de plantilla |

### reportes (reportes_bp.py)
| Método | Ruta | Función | Descripción |
|--------|------|---------|-------------|
| GET | `/reporte/<fecha>/<personal_id>` | reporte_persona_dia | Reporte HTML del día |
| GET | `/reporte/<fecha>/<personal_id>/pdf` | reporte_persona_dia_pdf | Reporte PDF del día |

### plantillas (plantillas_bp.py)
| Método | Ruta | Función | Descripción |
|--------|------|---------|-------------|
| GET | `/plantillas` | plantillas_panel | Panel principal de plantillas |
| POST | `/plantillas/crear` | plantillas_crear | Crear nueva plantilla |
| POST | `/plantillas/borrar/<plantilla_id>` | borrar_plantilla | Eliminar plantilla |
| POST | `/plantillas/<plantilla_id>/rename` | plantilla_rename | Renombrar plantilla |
| GET | `/plantillas/<plantilla_id>/dia/<dia_index>` | plantilla_dia | Editar día de plantilla |
| POST | `/plantillas/<plantilla_id>/item/add` | plantilla_item_add | Agregar item a plantilla |
| POST | `/plantillas/item/<item_id>/delete` | plantilla_item_delete | Eliminar item de plantilla |
| POST | `/plantillas/guardar_simple` | guardar_semana_como_plantilla_simple | Guardar semana como plantilla |
| POST | `/plantillas/aplicar_simple` | aplicar_plantilla_guardada_simple | Aplicar plantilla a semana |
| POST | `/plantillas/vaciar_semana` | vaciar_semana | Vaciar toda la semana |

### sop (sop_bp.py)
| Método | Ruta | Función | Descripción |
|--------|------|---------|-------------|
| GET | `/sop` | sop_panel | Panel principal de SOP |
| GET,POST | `/sop/crear/<subarea_id>` | sop_crear | Crear nuevo SOP |
| GET,POST | `/sop/<sop_id>/detalles` | sop_detalles | Editar detalles del SOP |
| GET,POST | `/sop/<sop_id>/elementoset` | sop_elementoset_edit | Editar elementos del SOP |
| GET | `/sop/<sop_id>/fracciones` | sop_fracciones_edit | Editar fracciones del SOP |
| GET,POST | `/sop-evento-crear` | sop_evento_crear | Crear SOP de evento |
| GET | `/sop-evento/<sop_evento_id>/editar` | sop_evento_editar | Editar SOP de evento |
| GET,POST | `/sop-evento/<sop_evento_id>/detalle` | sop_evento_detalle | Detalle de SOP evento |

### catalogos (catalogos_bp.py)
| Método | Ruta | Función | Descripción |
|--------|------|---------|-------------|
| GET | `/catalogos/quimicos-recetas` | quimicos_recetas | Gestión de químicos y recetas |
| GET | `/catalogos/consumos` | consumos | Gestión de consumos |
| GET | `/catalogos/regulares/elementos` | elementos | Gestión de elementos |
| GET | `/catalogos/herramientas` | herramientas | Gestión de herramientas |
| GET | `/catalogos/kits` | kits | Gestión de kits |
| GET | `/catalogos/fracciones` | fracciones | Gestión de fracciones |
| GET | `/catalogos/fracciones/<fraccion_id>/metodologias` | fraccion_metodologias | Metodologías de fracción |
| GET | `/catalogos/kits-eventos` | kits_eventos | Kits de eventos |
| GET | `/catalogos/fracciones-eventos` | fracciones_eventos | Fracciones de eventos |
| GET | `/catalogos/metodologias-eventos/<metodologia_id>` | metodologia_evento_detalle | Detalle metodología evento |

### api (api_bp.py)

#### Químicos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/quimicos/next-id` | api_quimicos_next_id |
| GET | `/api/quimicos/catalogos` | api_quimicos_catalogos |
| POST | `/api/quimicos` | api_quimicos_crear |
| PUT | `/api/quimicos/<quimico_id>` | api_quimicos_editar |
| DELETE | `/api/quimicos/<quimico_id>` | api_quimicos_eliminar |

#### Recetas
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/recetas/next-id` | api_recetas_next_id |
| GET | `/api/recetas/catalogos` | api_recetas_catalogos |
| GET | `/api/recetas/fracciones-disponibles` | api_recetas_fracciones_disponibles |
| POST | `/api/recetas` | api_recetas_crear |
| PUT | `/api/recetas/<receta_id>` | api_recetas_editar |
| DELETE | `/api/recetas/<receta_id>` | api_recetas_eliminar |

#### Consumos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/consumos/next-id` | api_consumos_next_id |
| POST | `/api/consumos` | api_consumos_crear |
| PUT | `/api/consumos/<consumo_id>` | api_consumos_editar |
| DELETE | `/api/consumos/<consumo_id>` | api_consumos_eliminar |

#### Elementos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/elementos` | api_elementos_list |
| GET | `/api/elementos/next-id` | api_elementos_next_id |
| GET | `/api/elementos/catalogos` | api_elementos_catalogos |
| POST | `/api/elementos` | api_elementos_create |
| PUT | `/api/elementos/<elemento_id>` | api_elementos_update |
| DELETE | `/api/elementos/<elemento_id>` | api_elementos_delete |

#### Herramientas
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/herramientas` | api_herramientas_listar |
| GET | `/api/herramientas/next-id` | api_herramientas_next_id |
| GET | `/api/herramientas/catalogos` | api_herramientas_catalogos |
| POST | `/api/herramientas` | api_herramientas_crear |
| PUT | `/api/herramientas/<herramienta_id>` | api_herramientas_editar |
| DELETE | `/api/herramientas/<herramienta_id>` | api_herramientas_eliminar |

#### Kits (Regulares)
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/kits` | api_kits_listar |
| GET | `/api/kits/next-id` | api_kits_next_id |
| GET | `/api/kits/herramientas-disponibles` | api_kits_herramientas_disponibles |
| GET | `/api/kits/fracciones-disponibles` | api_kits_fracciones_disponibles |
| POST | `/api/kits` | api_kits_crear |
| PUT | `/api/kits/<kit_id>` | api_kits_editar |
| DELETE | `/api/kits/<kit_id>` | api_kits_eliminar |

#### Fracciones (Regulares)
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/fracciones` | api_fracciones_listar |
| GET | `/api/fracciones/next-id` | api_fracciones_next_id |
| GET | `/api/fracciones/catalogos` | api_fracciones_catalogos |
| POST | `/api/fracciones` | api_fracciones_crear |
| PUT | `/api/fracciones/<fraccion_id>` | api_fracciones_editar |
| DELETE | `/api/fracciones/<fraccion_id>` | api_fracciones_eliminar |
| GET | `/api/fracciones/<fraccion_id>/metodologias` | api_fraccion_metodologias_get |
| POST | `/api/fracciones/<fraccion_id>/metodologias/<nivel_id>` | api_fraccion_metodologias_save |

#### Kits Eventos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/kits-eventos` | api_kits_eventos_listar |
| GET | `/api/kits-eventos/next-id` | api_kits_eventos_next_id |
| GET | `/api/kits-eventos/eventos-disponibles` | api_kits_eventos_eventos_disponibles |
| GET | `/api/kits-eventos/casos-disponibles` | api_kits_eventos_casos_disponibles |
| POST | `/api/kits-eventos` | api_kits_eventos_crear |
| PUT | `/api/kits-eventos/<kit_id>` | api_kits_eventos_editar |
| DELETE | `/api/kits-eventos/<kit_id>` | api_kits_eventos_eliminar |

#### Fracciones Eventos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/fracciones-eventos` | api_fracciones_eventos_listar |
| GET | `/api/fracciones-eventos/next-id` | api_fracciones_eventos_next_id |
| GET | `/api/fracciones-eventos/eventos-disponibles` | api_fracciones_eventos_eventos_disponibles |
| GET | `/api/fracciones-eventos/codigos-disponibles` | api_fracciones_eventos_codigos_disponibles |
| POST | `/api/fracciones-eventos` | api_fracciones_eventos_crear |
| PUT | `/api/fracciones-eventos/<fraccion_id>` | api_fracciones_eventos_editar |
| DELETE | `/api/fracciones-eventos/<fraccion_id>` | api_fracciones_eventos_eliminar |

#### Metodologías Eventos
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/metodologias-eventos/<metodologia_id>` | api_metodologia_evento_get |
| POST | `/api/metodologias-eventos/<metodologia_id>/pasos` | api_metodologia_evento_save_pasos |

#### Tareas
| Método | Ruta | Función |
|--------|------|---------|
| POST | `/api/tarea/<tarea_id>/check` | marcar_tarea_check |
| DELETE | `/api/tarea/<tarea_id>/check` | desmarcar_tarea_check |

#### SOP Verificación
| Método | Ruta | Función |
|--------|------|---------|
| GET | `/api/verificar_sop/<subarea_id>/<tipo_sop>` | verificar_sop_existe |
| GET | `/api/subareas_con_sop/<area_id>` | subareas_con_sop |

---

## Templates

### auth/
| Template | Usado por |
|----------|-----------|
| login.html | auth.login |

### home/
| Template | Usado por |
|----------|-----------|
| home.html | home.home, home.home_admin_panel |

### rutas/
| Template | Usado por |
|----------|-----------|
| mi_ruta.html | rutas.mi_ruta |
| ruta_dia.html | rutas.ruta_dia |
| plan_dia_form.html | rutas.plan_dia_asignar |
| asignacion_form.html | rutas.asignar_ruta |
| plantilla_dia_form.html | plantillas.plantilla_dia |

### plantillas/
| Template | Usado por |
|----------|-----------|
| plantillas_panel.html | plantillas.plantillas_panel |

### reportes/
| Template | Usado por |
|----------|-----------|
| reporte_personal.html | (legacy) |
| reporte_personal_dia.html | reportes.reporte_persona_dia |
| sop_macro_pdf.html | reportes.reporte_persona_dia_pdf |
| sop_micro_pdf.html | reportes.reporte_persona_dia_pdf |

### sop/
| Template | Usado por |
|----------|-----------|
| sop_panel.html | sop.sop_panel |
| sop_crear.html | sop.sop_crear |
| sop_detalles.html | sop.sop_detalles |
| sop_elementoset.html | sop.sop_elementoset_edit |
| sop_evento_crear.html | sop.sop_evento_crear |
| sop_evento_detalle.html | sop.sop_evento_detalle, sop.sop_evento_editar |

### catalogos/compartidos/
| Template | Usado por |
|----------|-----------|
| quimicos_recetas.html | catalogos.quimicos_recetas |
| consumos.html | catalogos.consumos |

### catalogos/regulares/
| Template | Usado por |
|----------|-----------|
| elementos.html | catalogos.elementos |
| herramientas.html | catalogos.herramientas |
| kits.html | catalogos.kits |
| fracciones.html | catalogos.fracciones |
| metodologias_fraccion.html | catalogos.fraccion_metodologias |

### catalogos/eventos/
| Template | Usado por |
|----------|-----------|
| kits_eventos.html | catalogos.kits_eventos |
| fracciones_eventos.html | catalogos.fracciones_eventos |
| metodologia_evento_detalle.html | catalogos.metodologia_evento_detalle |

### components/
| Template | Descripción |
|----------|-------------|
| sidebar_nav.html | Navegación lateral reutilizable |
| confirmacion_modal.html | Modal de confirmación reutilizable |

---

## Estructura de Archivos

```
app/
├── routes/
│   ├── __init__.py          # Registro de blueprints
│   ├── helpers.py            # Decoradores (admin_required, etc.)
│   ├── auth.py               # Blueprint auth
│   ├── home.py               # Blueprint home
│   ├── rutas_bp.py           # Blueprint rutas
│   ├── reportes_bp.py        # Blueprint reportes
│   ├── plantillas_bp.py      # Blueprint plantillas
│   ├── sop_bp.py             # Blueprint sop
│   ├── catalogos_bp.py       # Blueprint catalogos (HTML)
│   └── api_bp.py             # Blueprint api (REST)
│
├── templates/
│   ├── auth/
│   ├── home/
│   ├── rutas/
│   ├── plantillas/
│   ├── reportes/
│   ├── sop/
│   ├── catalogos/
│   │   ├── compartidos/
│   │   ├── regulares/
│   │   └── eventos/
│   └── components/
│
└── models.py                  # Modelos SQLAlchemy
```
