console.log('🚀 elementos.js cargado');

// =====================================================
// 🎯 SISTEMA DE GESTIÓN DE ELEMENTOS
// =====================================================

let catalogos = { areas: [], subareas: [], grupos: [], descripciones_por_grupo: {} };
let elementosData = [];
let paginaActual = 1;
let totalPaginas = 1;
let modoEdicion = false;
let elementoIdEdicion = null;

// ========== CARGA INICIAL ==========
document.addEventListener('DOMContentLoaded', async function() {
    console.log('✅ DOM cargado');
    
    try {
        console.log('🔄 Iniciando carga de catálogos...');
        await cargarCatalogos();
        console.log('✅ Catálogos cargados');
        
        console.log('🔄 Iniciando carga de elementos...');
        await cargarElementos();
        console.log('✅ Elementos cargados');
        
        console.log('🔄 Configurando event listeners...');
        setupEventListeners();
        console.log('✅ Event listeners configurados');
        
    } catch (error) {
        console.error('❌ Error en carga inicial:', error);
    }
});

// ========== SETUP EVENT LISTENERS ==========
function setupEventListeners() {
    // Botón agregar elemento
    const btnAgregar = document.getElementById('btn-agregar-elemento');
    if (btnAgregar) {
        btnAgregar.addEventListener('click', function() {
            console.log('Click en agregar elemento');
            abrirModalNuevo();
        });
    }
    
    // Filtros
    const filterArea = document.getElementById('filter-area');
    if (filterArea) {
        filterArea.addEventListener('change', function() {
            console.log('Cambio en filter-area:', this.value);
            cargarSubareasFiltro(this.value);
            cargarElementos();
            actualizarBotonLimpiarFiltros();
        });
    }
    
    const filterSubarea = document.getElementById('filter-subarea');
    if (filterSubarea) {
        filterSubarea.addEventListener('change', function() {
            console.log('Cambio en filter-subarea:', this.value);
            cargarElementos();
            actualizarBotonLimpiarFiltros();
        });
    }
    
    // Botón limpiar filtros
    const btnClearFilters = document.getElementById('btn-clear-filters');
    if (btnClearFilters) {
        btnClearFilters.addEventListener('click', limpiarFiltros);
    }
    
    // Paginación
    const btnPrevPage = document.getElementById('btn-prev-page');
    if (btnPrevPage) {
        btnPrevPage.addEventListener('click', function() {
            if (paginaActual > 1) {
                cargarElementos(paginaActual - 1);
            }
        });
    }
    
    const btnNextPage = document.getElementById('btn-next-page');
    if (btnNextPage) {
        btnNextPage.addEventListener('click', function() {
            if (paginaActual < totalPaginas) {
                cargarElementos(paginaActual + 1);
            }
        });
    }
    
    // Modal - cerrar
    const modalClose = document.getElementById('modal-elemento-close');
    if (modalClose) {
        modalClose.addEventListener('click', cerrarModal);
    }
    
    const modalCancel = document.getElementById('modal-elemento-cancel');
    if (modalCancel) {
        modalCancel.addEventListener('click', cerrarModal);
    }
    
    // Modal - overlay click
    const modalOverlay = document.getElementById('modal-elemento');
    if (modalOverlay) {
        modalOverlay.addEventListener('click', function(e) {
            if (e.target === this) {
                cerrarModal();
            }
        });
    }
    
    // Formulario
    const formElemento = document.getElementById('form-elemento');
    if (formElemento) {
        formElemento.addEventListener('submit', function(e) {
            e.preventDefault();
            console.log('Submit form-elemento');
            guardarElemento();
        });
    }
    
    // Modal - botón guardar
    const modalSave = document.getElementById('modal-elemento-save');
    if (modalSave) {
        modalSave.addEventListener('click', function(e) {
            e.preventDefault();
            const form = document.getElementById('form-elemento');
            if (form) {
                form.dispatchEvent(new Event('submit'));
            }
        });
    }
    
    // Área del modal
    const elementoArea = document.getElementById('elemento-area');
    if (elementoArea) {
        elementoArea.addEventListener('change', function() {
            console.log('Cambio en elemento-area:', this.value);
            cargarSubareasModal(this.value);
        });
    }
    
    // Nombre del modal
    const elementoNombre = document.getElementById('elemento-nombre');
    if (elementoNombre) {
        elementoNombre.addEventListener('change', function() {
            console.log('Cambio en elemento-nombre:', this.value);
            cargarDescripciones(this.value);
            generarPreviewId();
        });
    }
}

// ========== ACTUALIZAR BOTÓN LIMPIAR FILTROS ==========
function actualizarBotonLimpiarFiltros() {
    const btnClearFilters = document.getElementById('btn-clear-filters');
    const filterArea = document.getElementById('filter-area');
    const filterSubarea = document.getElementById('filter-subarea');
    
    if (!btnClearFilters) return;
    
    const hayFiltros = (filterArea && filterArea.value) || (filterSubarea && filterSubarea.value);
    btnClearFilters.style.display = hayFiltros ? 'inline-flex' : 'none';
}

// ========== CARGAR CATÁLOGOS ==========
async function cargarCatalogos() {
    try {
        console.log('📡 Fetching /api/elementos/catalogos');
        const response = await fetch('/api/elementos/catalogos');
        console.log('📡 Response status:', response.status);
        
        if (!response.ok) throw new Error('Error al cargar catálogos');
        
        catalogos = await response.json();
        console.log('📦 Catálogos recibidos:', catalogos);
        
        // Poblar filtros
        const filterArea = document.getElementById('filter-area');
        if (filterArea) {
            filterArea.innerHTML = '<option value="">Todas las áreas</option>';
            catalogos.areas.forEach(area => {
                const option = document.createElement('option');
                option.value = area.area_id;
                option.textContent = area.nombre;
                filterArea.appendChild(option);
            });
            console.log('✅ Filter areas poblado');
        }
        
        // Poblar modal - áreas
        const elementoArea = document.getElementById('elemento-area');
        if (elementoArea) {
            elementoArea.innerHTML = '<option value="">Seleccionar área...</option>';
            catalogos.areas.forEach(area => {
                const option = document.createElement('option');
                option.value = area.area_id;
                option.textContent = area.nombre;
                elementoArea.appendChild(option);
            });
            console.log('✅ Modal areas poblado');
        }
        
        // Poblar modal - nombres/grupos
        const elementoNombre = document.getElementById('elemento-nombre');
        if (elementoNombre) {
            elementoNombre.innerHTML = '<option value="">Seleccionar grupo...</option>';
            catalogos.grupos.forEach(grupo => {
                const option = document.createElement('option');
                option.value = grupo;
                option.textContent = grupo;
                elementoNombre.appendChild(option);
            });
            console.log('✅ Modal grupos poblado');
        }
        
    } catch (error) {
        console.error('❌ Error en cargarCatalogos:', error);
        mostrarAlerta('Error al cargar catálogos', 'danger');
    }
}

// ========== CARGAR SUBÁREAS (MODAL) ==========
function cargarSubareasModal(areaId) {
    console.log('cargarSubareasModal llamado con:', areaId);
    const elementoSubarea = document.getElementById('elemento-subarea');
    if (!elementoSubarea) {
        console.warn('elemento-subarea no encontrado');
        return;
    }
    
    elementoSubarea.innerHTML = '<option value="">Seleccionar subárea...</option>';
    
    if (!areaId) {
        elementoSubarea.disabled = true;
        return;
    }
    
    const subareasFiltradas = catalogos.subareas.filter(sa => sa.area_id == areaId);
    console.log('Subáreas filtradas:', subareasFiltradas);
    
    subareasFiltradas.forEach(subarea => {
        const option = document.createElement('option');
        option.value = subarea.subarea_id;
        option.textContent = subarea.nombre;
        elementoSubarea.appendChild(option);
    });
    
    elementoSubarea.disabled = false;
}

// ========== CARGAR SUBÁREAS (FILTRO) ==========
function cargarSubareasFiltro(areaId) {
    console.log('cargarSubareasFiltro llamado con:', areaId);
    const filterSubarea = document.getElementById('filter-subarea');
    if (!filterSubarea) {
        console.warn('filter-subarea no encontrado');
        return;
    }
    
    filterSubarea.innerHTML = '<option value="">Todas las subáreas</option>';
    
    if (!areaId) {
        filterSubarea.disabled = true;
        filterSubarea.value = '';
        return;
    }
    
    const subareasFiltradas = catalogos.subareas.filter(sa => sa.area_id == areaId);
    console.log('Subáreas filtradas para filtro:', subareasFiltradas);
    
    subareasFiltradas.forEach(subarea => {
        const option = document.createElement('option');
        option.value = subarea.subarea_id;
        option.textContent = subarea.nombre;
        filterSubarea.appendChild(option);
    });
    
    filterSubarea.disabled = false;
}

// ========== CARGAR DESCRIPCIONES ==========
function cargarDescripciones(nombre) {
    console.log('cargarDescripciones llamado con:', nombre);
    const descripcionField = document.getElementById('elemento-descripcion');
    if (!descripcionField) {
        console.warn('elemento-descripcion no encontrado');
        return;
    }
    
    const parent = descripcionField.parentNode;
    
    if (!nombre) {
        if (descripcionField.tagName !== 'SELECT') {
            const newSelect = document.createElement('select');
            newSelect.id = 'elemento-descripcion';
            newSelect.className = 'form-select';
            newSelect.required = true;
            newSelect.disabled = true;
            newSelect.innerHTML = '<option value="">Selecciona un grupo primero</option>';
            parent.replaceChild(newSelect, descripcionField);
        } else {
            descripcionField.innerHTML = '<option value="">Selecciona un grupo primero</option>';
            descripcionField.disabled = true;
        }
        return;
    }
    
    const descripciones = catalogos.descripciones_por_grupo[nombre] || [];
    console.log(`Descripciones para "${nombre}":`, descripciones);
    
    // Si NO hay descripciones para este nombre, permitir escribir libremente
    if (descripciones.length === 0) {
        console.log('No hay descripciones, convirtiendo a input');
        const newInput = document.createElement('input');
        newInput.type = 'text';
        newInput.id = 'elemento-descripcion';
        newInput.className = 'form-input';
        newInput.placeholder = 'Escribir descripción...';
        newInput.required = true;
        newInput.addEventListener('input', generarPreviewId);
        parent.replaceChild(newInput, descripcionField);
        return;
    }
    
    // Si SÍ hay descripciones, mostrar el select con las opciones
    console.log('Hay descripciones, mostrando select');
    if (descripcionField.tagName !== 'SELECT') {
        const newSelect = document.createElement('select');
        newSelect.id = 'elemento-descripcion';
        newSelect.className = 'form-select';
        newSelect.required = true;
        newSelect.innerHTML = '<option value="">Seleccionar descripción...</option>';
        descripciones.forEach(desc => {
            const option = document.createElement('option');
            option.value = desc;
            option.textContent = desc;
            newSelect.appendChild(option);
        });
        newSelect.disabled = false;
        newSelect.addEventListener('change', generarPreviewId);
        parent.replaceChild(newSelect, descripcionField);
    } else {
        descripcionField.innerHTML = '<option value="">Seleccionar descripción...</option>';
        descripciones.forEach(desc => {
            const option = document.createElement('option');
            option.value = desc;
            option.textContent = desc;
            descripcionField.appendChild(option);
        });
        descripcionField.disabled = false;
    }
}

// ========== GENERAR PREVIEW ID ==========
async function generarPreviewId() {
    console.log('generarPreviewId llamado');
    const nombre = document.getElementById('elemento-nombre').value;
    const descripcionField = document.getElementById('elemento-descripcion');
    const descripcion = descripcionField ? descripcionField.value : '';
    const previewGroup = document.getElementById('elemento-id-preview-group');
    const previewElement = document.getElementById('elemento-id-preview');
    
    console.log('Nombre:', nombre, 'Descripción:', descripcion);
    
    if (!nombre || !descripcion) {
        if (previewGroup) previewGroup.style.display = 'none';
        return;
    }
    
    try {
        const url = `/api/elementos/next-id?nombre=${encodeURIComponent(nombre)}&descripcion=${encodeURIComponent(descripcion)}`;
        console.log('Fetching:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Error al generar ID');
        
        const data = await response.json();
        console.log('Preview ID generado:', data.next_id);
        
        if (previewElement) {
            previewElement.value = data.next_id;
        }
        if (previewGroup) {
            previewGroup.style.display = 'block';
        }
    } catch (error) {
        console.error('Error al generar preview ID:', error);
    }
}

// ========== CARGAR ELEMENTOS ==========
async function cargarElementos(pagina = 1) {
    console.log('cargarElementos llamado con página:', pagina);
    
    try {
        const filterArea = document.getElementById('filter-area');
        const filterSubarea = document.getElementById('filter-subarea');
        
        const areaId = filterArea ? filterArea.value : '';
        const subareaId = filterSubarea ? filterSubarea.value : '';
        
        console.log('Filtros - Area:', areaId, 'Subarea:', subareaId);
        
        const params = new URLSearchParams({
            page: pagina,
            per_page: 20
        });
        
        if (subareaId) {
            params.append('subarea_id', subareaId);
        } else if (areaId) {
            params.append('area_id', areaId);
        }
        
        const url = `/api/elementos?${params}`;
        console.log('Fetching:', url);
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Error al cargar elementos');
        
        const data = await response.json();
        console.log('Elementos recibidos:', data);
        
        elementosData = data.elementos;
        paginaActual = data.current_page;
        totalPaginas = data.pages;
        
        renderizarTabla();
        actualizarPaginacion(data);
        
    } catch (error) {
        console.error('❌ Error en cargarElementos:', error);
        mostrarAlerta('Error al cargar elementos', 'danger');
    }
}

// ========== RENDERIZAR TABLA ==========
function renderizarTabla() {
    console.log('renderizarTabla llamado');
    const tablaContainer = document.getElementById('tabla-container');
    const elementosCount = document.getElementById('elementos-count');
    const paginationContainer = document.getElementById('pagination-container');
    
    console.log('tabla-container:', tablaContainer);
    console.log('elementos-count:', elementosCount);
    
    if (!tablaContainer) {
        console.warn('tabla-container no encontrado');
        return;
    }
    
    if (elementosData.length === 0) {
        console.log('No hay elementos, mostrando empty state');
        tablaContainer.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🧩</div>
                <div class="empty-state-text">No hay elementos</div>
                <div class="empty-state-sub">Agrega el primer elemento o ajusta los filtros</div>
            </div>
        `;
        if (elementosCount) elementosCount.textContent = 'No hay elementos';
        if (paginationContainer) paginationContainer.style.display = 'none';
        return;
    }
    
    console.log(`Renderizando ${elementosData.length} elementos`);
    
    if (elementosCount) {
        elementosCount.textContent = `Elementos (${elementosData.length})`;
    }
    
    if (paginationContainer) {
        paginationContainer.style.display = 'flex';
    }
    
    const tabla = `
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Grupo</th>
                    <th>Descripción</th>
                    <th>SubÁrea</th>
                    <th>Área</th>
                    <th>Cantidad</th>
                    <th>Estatus</th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                ${elementosData.map(elem => `
                    <tr>
                        <td><code>${elem.elemento_id}</code></td>
                        <td><strong>${elem.nombre}</strong></td>
                        <td>${elem.descripcion || '—'}</td>
                        <td>${elem.subarea_nombre}</td>
                        <td>${elem.area_nombre}</td>
                        <td>${elem.cantidad}</td>
                        <td>
                            <span class="badge ${elem.estatus === 'ACTIVO' ? 'badge-success' : 'badge-secondary'}">
                                ${elem.estatus}
                            </span>
                        </td>
                        <td>
                            <div class="actions">
                                <button class="btn-icon" onclick="editarElemento('${elem.elemento_id}')" title="Editar">
                                    ✏️
                                </button>
                                <button class="btn-icon btn-delete" onclick="eliminarElemento('${elem.elemento_id}')" title="Eliminar">
                                    🗑️
                                </button>
                            </div>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    
    tablaContainer.innerHTML = tabla;
    console.log('✅ Tabla renderizada');
}

// ========== ACTUALIZAR PAGINACIÓN ==========
function actualizarPaginacion(data) {
    console.log('actualizarPaginacion llamado con:', data);
    const paginationInfo = document.getElementById('pagination-info');
    const btnPrevPage = document.getElementById('btn-prev-page');
    const btnNextPage = document.getElementById('btn-next-page');
    
    if (paginationInfo) {
        const desde = (data.current_page - 1) * data.per_page + 1;
        const hasta = Math.min(data.current_page * data.per_page, data.total);
        paginationInfo.textContent = `${desde}-${hasta} de ${data.total}`;
        console.log('✅ Paginación info actualizada');
    }
    
    if (btnPrevPage) {
        btnPrevPage.disabled = data.current_page === 1;
    }
    
    if (btnNextPage) {
        btnNextPage.disabled = data.current_page === data.pages;
    }
}

// ========== LIMPIAR FILTROS ==========
function limpiarFiltros() {
    console.log('limpiarFiltros llamado');
    const filterArea = document.getElementById('filter-area');
    const filterSubarea = document.getElementById('filter-subarea');
    
    if (filterArea) filterArea.value = '';
    if (filterSubarea) {
        filterSubarea.value = '';
        filterSubarea.disabled = true;
    }
    
    actualizarBotonLimpiarFiltros();
    cargarElementos();
}

// ========== ABRIR MODAL NUEVO ==========
function abrirModalNuevo() {
    console.log('abrirModalNuevo llamado');
    modoEdicion = false;
    elementoIdEdicion = null;
    
    const modalTitle = document.getElementById('modal-elemento-title');
    const modalSave = document.getElementById('modal-elemento-save');
    const previewGroup = document.getElementById('elemento-id-preview-group');
    const estatusGroup = document.getElementById('elemento-estatus-group');
    
    if (modalTitle) modalTitle.textContent = 'Agregar Elemento';
    if (modalSave) modalSave.textContent = 'Guardar Elemento';
    if (previewGroup) previewGroup.style.display = 'none';
    if (estatusGroup) estatusGroup.style.display = 'none';
    
    // Reset form
    const formElemento = document.getElementById('form-elemento');
    if (formElemento) formElemento.reset();
    
    // Habilitar campos
    const elementoArea = document.getElementById('elemento-area');
    const elementoSubarea = document.getElementById('elemento-subarea');
    const elementoNombre = document.getElementById('elemento-nombre');
    
    if (elementoArea) elementoArea.disabled = false;
    if (elementoSubarea) {
        elementoSubarea.disabled = true;
        elementoSubarea.innerHTML = '<option value="">Selecciona un área primero</option>';
    }
    if (elementoNombre) elementoNombre.disabled = false;
    
    // Reset descripción a select
    const descripcionField = document.getElementById('elemento-descripcion');
    if (descripcionField && descripcionField.tagName === 'INPUT') {
        const parent = descripcionField.parentNode;
        const newSelect = document.createElement('select');
        newSelect.id = 'elemento-descripcion';
        newSelect.className = 'form-select';
        newSelect.required = true;
        newSelect.disabled = true;
        newSelect.innerHTML = '<option value="">Selecciona un grupo primero</option>';
        parent.replaceChild(newSelect, descripcionField);
    }
    
    // Si hay filtros activos, pre-seleccionar área y subárea
    const filterArea = document.getElementById('filter-area');
    const filterSubarea = document.getElementById('filter-subarea');
    
    if (filterArea && filterArea.value) {
        if (elementoArea) {
            elementoArea.value = filterArea.value;
            cargarSubareasModal(filterArea.value);
            
            // Si también hay subárea filtrada, pre-seleccionarla
            if (filterSubarea && filterSubarea.value) {
                setTimeout(() => {
                    if (elementoSubarea) {
                        elementoSubarea.value = filterSubarea.value;
                    }
                }, 100);
            }
        }
    }
    
    // Mostrar modal
    const modal = document.getElementById('modal-elemento');
    if (modal) {
        modal.classList.add('active');
        console.log('✅ Modal mostrado');
    } else {
        console.warn('modal-elemento no encontrado');
    }
}

// ========== CERRAR MODAL ==========
function cerrarModal() {
    console.log('cerrarModal llamado');
    const modal = document.getElementById('modal-elemento');
    if (modal) {
        modal.classList.remove('active');
        console.log('✅ Modal cerrado');
    }
}

// ========== GUARDAR ELEMENTO ==========
async function guardarElemento() {
    console.log('guardarElemento llamado');
    
    try {
        const subareaId = document.getElementById('elemento-subarea').value;
        const nombre = document.getElementById('elemento-nombre').value;
        const descripcionField = document.getElementById('elemento-descripcion');
        const descripcion = descripcionField ? descripcionField.value : '';
        const cantidad = parseFloat(document.getElementById('elemento-cantidad').value);
        const estatus = document.getElementById('elemento-estatus').value || 'ACTIVO';
        
        console.log('Datos del formulario:', { subareaId, nombre, descripcion, cantidad, estatus });
        
        if (!subareaId || !nombre || !descripcion || !cantidad) {
            mostrarAlerta('Por favor complete todos los campos requeridos', 'warning');
            return;
        }
        
        if (modoEdicion) {
            console.log('Modo EDITAR, ID:', elementoIdEdicion);
            const response = await fetch(`/api/elementos/${elementoIdEdicion}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cantidad, estatus })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Error al actualizar elemento');
            }
            
            mostrarAlerta('Elemento actualizado exitosamente', 'success');
        } else {
            console.log('Modo CREAR');
            const response = await fetch('/api/elementos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subarea_id: subareaId,
                    nombre: nombre,
                    descripcion: descripcion,
                    cantidad: cantidad
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Error al crear elemento');
            }
            
            mostrarAlerta('Elemento creado exitosamente', 'success');
        }
        
        cerrarModal();
        await cargarElementos(paginaActual);
        
    } catch (error) {
        console.error('❌ Error en guardarElemento:', error);
        mostrarAlerta(error.message, 'danger');
    }
}

// ========== EDITAR ELEMENTO ==========
function editarElemento(elementoId) {
    console.log('editarElemento llamado con ID:', elementoId);
    const elemento = elementosData.find(e => e.elemento_id === elementoId);
    
    if (!elemento) {
        console.error('Elemento no encontrado:', elementoId);
        mostrarAlerta('Elemento no encontrado', 'danger');
        return;
    }
    
    console.log('Elemento encontrado:', elemento);
    
    modoEdicion = true;
    elementoIdEdicion = elemento.elemento_id;
    
    const modalTitle = document.getElementById('modal-elemento-title');
    const modalSave = document.getElementById('modal-elemento-save');
    const previewGroup = document.getElementById('elemento-id-preview-group');
    const estatusGroup = document.getElementById('elemento-estatus-group');
    
    if (modalTitle) modalTitle.textContent = 'Editar Elemento';
    if (modalSave) modalSave.textContent = 'Actualizar';
    if (previewGroup) previewGroup.style.display = 'none';
    if (estatusGroup) estatusGroup.style.display = 'block';
    
    // Cargar datos
    const elementoArea = document.getElementById('elemento-area');
    const elementoSubarea = document.getElementById('elemento-subarea');
    const elementoNombre = document.getElementById('elemento-nombre');
    const elementoCantidad = document.getElementById('elemento-cantidad');
    const elementoEstatus = document.getElementById('elemento-estatus');
    
    if (elementoArea) {
        elementoArea.value = elemento.area_id;
        elementoArea.disabled = true;
    }
    
    cargarSubareasModal(elemento.area_id);
    setTimeout(() => {
        if (elementoSubarea) {
            elementoSubarea.value = elemento.subarea_id;
            elementoSubarea.disabled = true;
        }
    }, 100);
    
    if (elementoNombre) {
        elementoNombre.value = elemento.nombre;
        elementoNombre.disabled = true;
    }
    
    cargarDescripciones(elemento.nombre);
    setTimeout(() => {
        const descripcionField = document.getElementById('elemento-descripcion');
        if (descripcionField) {
            descripcionField.value = elemento.descripcion;
            descripcionField.disabled = true;
        }
    }, 100);
    
    if (elementoCantidad) elementoCantidad.value = elemento.cantidad;
    if (elementoEstatus) elementoEstatus.value = elemento.estatus;
    
    // Mostrar modal
    const modal = document.getElementById('modal-elemento');
    if (modal) {
        modal.classList.add('active');
        console.log('✅ Modal de edición mostrado');
    }
}

// ========== ELIMINAR ELEMENTO ==========
async function eliminarElemento(elementoId) {
    console.log('eliminarElemento llamado con ID:', elementoId);
    
    if (!confirm('¿Está seguro de eliminar este elemento?')) {
        console.log('Eliminación cancelada por el usuario');
        return;
    }
    
    try {
        const response = await fetch(`/api/elementos/${elementoId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Error al eliminar elemento');
        }
        
        console.log('✅ Elemento eliminado');
        mostrarAlerta('Elemento eliminado exitosamente', 'success');
        await cargarElementos(paginaActual);
        
    } catch (error) {
        console.error('❌ Error en eliminarElemento:', error);
        mostrarAlerta(error.message, 'danger');
    }
}

// ========== ALERTAS ==========
function mostrarAlerta(mensaje, tipo) {
    console.log(`Alerta ${tipo}:`, mensaje);
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${tipo}`;
    alert.textContent = mensaje;
    alert.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 10000;
        padding: 15px 20px;
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        background: ${tipo === 'success' ? '#28a745' : tipo === 'danger' ? '#dc3545' : '#ffc107'};
        color: white;
        font-weight: 500;
    `;
    
    document.body.appendChild(alert);
    
    setTimeout(() => {
        alert.remove();
    }, 3000);
}

console.log('✅ elementos.js completamente cargado');