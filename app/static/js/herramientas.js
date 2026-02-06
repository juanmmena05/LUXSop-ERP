// ===== HERRAMIENTAS - CRUD COMPLETO =====
(function() {
  'use strict';

  let modoModal = 'crear';
  let herramientaActualId = null;
  let gruposDisponibles = [];
  let herramientasCache = [];
  
  const filtroGrupo = document.getElementById('filtroGrupo');
  const filtroEstatus = document.getElementById('filtroEstatus');
  const tablaContainer = document.getElementById('tablaContainer');

  // ===== INICIALIZAR =====
  async function init() {
    await cargarGrupos();
    await cargarHerramientas();
    
    // Event listeners de filtros
    filtroGrupo?.addEventListener('change', aplicarFiltros);
    filtroEstatus?.addEventListener('change', aplicarFiltros);
  }

  // ===== CARGAR GRUPOS =====
  async function cargarGrupos() {
    try {
      const response = await fetch('/api/herramientas/catalogos');
      const data = await response.json();
      
      if (data.success) {
        gruposDisponibles = data.grupos;
        
        // Poblar dropdown del modal
        const selectModal = document.getElementById('herramientaGrupo');
        selectModal.innerHTML = '<option value="">Seleccionar grupo...</option>';
        
        data.grupos.forEach(g => {
          const option = document.createElement('option');
          option.value = g.codigo;
          option.textContent = `${g.codigo} - ${g.nombre}`;
          option.dataset.nombre = g.nombre;
          selectModal.appendChild(option);
        });
        
        // Poblar filtro
        const selectFiltro = document.getElementById('filtroGrupo');
        selectFiltro.innerHTML = '<option value="">Todos los grupos</option>';
        
        data.grupos.forEach(g => {
          const option = document.createElement('option');
          option.value = g.codigo;
          option.textContent = `${g.codigo} - ${g.nombre}`;
          selectFiltro.appendChild(option);
        });
      }
    } catch (error) {
      console.error('❌ Error al cargar grupos:', error);
    }
  }

  // ===== CARGAR HERRAMIENTAS =====
  async function cargarHerramientas() {
    try {
      const response = await fetch('/api/herramientas?per_page=1000');
      const data = await response.json();
      
      if (data.success) {
        herramientasCache = data.herramientas;
        aplicarFiltros();
      }
    } catch (error) {
      console.error('❌ Error al cargar herramientas:', error);
      tablaContainer.innerHTML = '<p style="text-align:center;color:#888;">Error al cargar herramientas</p>';
    }
  }

  // ===== APLICAR FILTROS =====
  function aplicarFiltros() {
    const grupoFiltro = filtroGrupo.value;
    const estatusFiltro = filtroEstatus.value;
    
    let herramientasFiltradas = herramientasCache;
    
    if (grupoFiltro) {
      herramientasFiltradas = herramientasFiltradas.filter(h => h.grupo === grupoFiltro);
    }
    
    if (estatusFiltro) {
      herramientasFiltradas = herramientasFiltradas.filter(h => h.estatus === estatusFiltro);
    }
    
    renderTabla(herramientasFiltradas);
  }

  // ===== RENDERIZAR TABLA =====
  function renderTabla(herramientas) {
    if (herramientas.length === 0) {
      tablaContainer.innerHTML = `
        <div class="empty-state">
          <div style="font-size:3rem;margin-bottom:12px;">🔧</div>
          <div style="font-size:1.1rem;margin-bottom:8px;">No hay herramientas</div>
          <div style="font-size:.9rem;color:#999;">Agrega tu primera herramienta</div>
        </div>
      `;
      return;
    }
    
    const html = `
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Grupo</th>
            <th>Nombre</th>
            <th>Descripción</th>
            <th>Estatus</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          ${herramientas.map(h => `
            <tr>
              <td><code>${h.herramienta_id}</code></td>
              <td>${h.grupo}</td>
              <td><strong>${h.nombre}</strong></td>
              <td>${h.descripcion}</td>
              <td>
                <span class="badge badge-${h.estatus.toLowerCase()}">
                  ${h.estatus}
                </span>
              </td>
              <td>
                <div class="actions">
                  <button class="btn-icon btn-editar-herramienta"
                          data-id="${h.herramienta_id}"
                          data-nombre="${h.nombre}"
                          data-descripcion="${h.descripcion}"
                          data-estatus="${h.estatus}"
                          title="Editar">
                    ✏️
                  </button>
                  <button class="btn-icon btn-delete btn-eliminar-herramienta"
                          data-id="${h.herramienta_id}"
                          data-nombre="${h.nombre}"
                          title="Eliminar">
                    🗑️
                  </button>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
    
    tablaContainer.innerHTML = html;
  }

  // ===== GENERAR ID AL SELECCIONAR GRUPO =====
  document.getElementById('herramientaGrupo')?.addEventListener('change', async function() {
    const grupo = this.value;
    
    if (!grupo) {
      document.getElementById('herramientaId').value = '';
      return;
    }
    
    try {
      const response = await fetch(`/api/herramientas/next-id?grupo=${grupo}`);
      const data = await response.json();
      
      if (data.success) {
        document.getElementById('herramientaId').value = data.herramienta_id;
      }
    } catch (error) {
      console.error('❌ Error al obtener ID:', error);
    }
  });

  // ===== ABRIR MODAL =====
  function abrirModal(modo, id = null, nombre_grupo = '', descripcion = '', estatus = 'Activo') {
    modoModal = modo;
    herramientaActualId = id;

    const modal = document.getElementById('modalHerramienta');
    const titulo = document.getElementById('modalHerramientaTitulo');
    const grupoField = document.getElementById('grupoField');
    const estatusField = document.getElementById('estatusField');
    const grupoSelect = document.getElementById('herramientaGrupo');
    const idInput = document.getElementById('herramientaId');
    const descripcionInput = document.getElementById('herramientaDescripcion');
    const estatusSelect = document.getElementById('herramientaEstatus');

    // Limpiar form
    document.getElementById('formHerramienta').reset();
    idInput.value = '';

    if (modo === 'crear') {
      titulo.textContent = 'Agregar Herramienta';
      grupoField.style.display = 'block';
      estatusField.style.display = 'none';
      grupoSelect.setAttribute('required', '');

    } else if (modo === 'editar') {
      titulo.textContent = 'Editar Herramienta';
      grupoField.style.display = 'none';
      estatusField.style.display = 'block';
      grupoSelect.removeAttribute('required');
      
      idInput.value = id;
      descripcionInput.value = descripcion;
      estatusSelect.value = estatus;
    }

    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }

  // ===== CERRAR MODAL =====
  function cerrarModal() {
    const modal = document.getElementById('modalHerramienta');
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
    
    document.getElementById('formHerramienta').reset();
    document.getElementById('herramientaId').value = '';
    document.getElementById('grupoField').style.display = 'block';
    document.getElementById('estatusField').style.display = 'none';
    modoModal = 'crear';
    herramientaActualId = null;
  }

  // ===== GUARDAR HERRAMIENTA =====
  async function guardarHerramienta(event) {
    event.preventDefault();

    const btnGuardar = document.getElementById('btnGuardarHerramienta');
    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';

    try {
      let response, data;

      if (modoModal === 'crear') {
        const grupoSelect = document.getElementById('herramientaGrupo');
        const grupo = grupoSelect.value;
        
        // Obtener el nombre del grupo desde el glosario
        const grupoOption = grupoSelect.options[grupoSelect.selectedIndex];
        const nombreGrupo = grupoOption.textContent.split(' - ')[1]; // "CA - CARRITO" → "CARRITO"
        
        const descripcion = document.getElementById('herramientaDescripcion').value.trim();

        response = await fetch('/api/herramientas', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            grupo, 
            nombre: nombreGrupo,  // ← Nombre viene del glosario automáticamente
            descripcion 
          })
        });

      } else if (modoModal === 'editar') {
        // Al editar, obtener el nombre actual desde la tabla (ya no hay input)
        const herramienta = herramientasCache.find(h => h.herramienta_id === herramientaActualId);
        const nombre = herramienta ? herramienta.nombre : '';
        
        const descripcion = document.getElementById('herramientaDescripcion').value.trim();
        const estatus = document.getElementById('herramientaEstatus').value;

        response = await fetch(`/api/herramientas/${herramientaActualId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ nombre, descripcion, estatus })
        });
      }

      data = await response.json();

      if (data.success) {
        alert(modoModal === 'crear' ? 'Herramienta creada correctamente' : 'Herramienta actualizada correctamente');
        cerrarModal();
        await cargarHerramientas();
      } else {
        alert('Error: ' + data.error);
      }

    } catch (error) {
      console.error('❌ Error:', error);
      alert('Error de conexión');
    } finally {
      btnGuardar.disabled = false;
      btnGuardar.textContent = 'Guardar';
    }
  }

  // ===== ELIMINAR HERRAMIENTA =====
  async function eliminarHerramienta(id, nombre) {
    const confirmar = confirm(
      `¿Estás seguro de eliminar la herramienta ${id} (${nombre})?\n\n` +
      `Esta acción no se puede deshacer.`
    );

    if (!confirmar) return;

    try {
      const response = await fetch(`/api/herramientas/${id}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        alert('Herramienta eliminada correctamente');
        await cargarHerramientas();
      } else {
        alert('Error: ' + data.error);
      }

    } catch (error) {
      console.error('❌ Error:', error);
      alert('Error de conexión');
    }
  }

  // ===== EVENT LISTENERS =====
  document.querySelector('.btn-agregar-herramienta')?.addEventListener('click', function() {
    abrirModal('crear');
  });

  document.querySelector('.modal-close')?.addEventListener('click', cerrarModal);
  document.querySelector('.modal-overlay')?.addEventListener('click', cerrarModal);
  document.querySelector('.btn-cancel-herramienta')?.addEventListener('click', cerrarModal);

  document.getElementById('formHerramienta')?.addEventListener('submit', guardarHerramienta);

  document.addEventListener('click', function(e) {
    if (e.target.closest('.btn-editar-herramienta')) {
      const btn = e.target.closest('.btn-editar-herramienta');
      abrirModal('editar', btn.dataset.id, '', btn.dataset.descripcion, btn.dataset.estatus);
    }

    if (e.target.closest('.btn-eliminar-herramienta')) {
      const btn = e.target.closest('.btn-eliminar-herramienta');
      eliminarHerramienta(btn.dataset.id, btn.dataset.nombre);
    }
  });

  // ✅ Inicializar al cargar la página
  init();

})();