// ===== KITS - CRUD COMPLETO CON CHECKBOXES =====
(function() {
  'use strict';

  let modoModal = 'crear';
  let kitActualId = null;
  let fraccionesDisponibles = [];
  let herramientasDisponibles = [];
  let gruposHerramientas = [];
  let kitsCache = [];
  
  const filtroFraccion = document.getElementById('filtroFraccion');
  const filtroNivel = document.getElementById('filtroNivel');
  const tablaContainer = document.getElementById('tablaContainer');

  // ===== INICIALIZAR =====
  async function init() {
    await cargarGruposHerramientas();
    await cargarFracciones();
    await cargarKits();
    
    filtroFraccion?.addEventListener('change', aplicarFiltros);
    filtroNivel?.addEventListener('change', aplicarFiltros);
  }

  // ===== CARGAR GRUPOS DE HERRAMIENTAS =====
  async function cargarGruposHerramientas() {
    try {
      const response = await fetch('/api/herramientas/catalogos');
      const data = await response.json();
      
      if (data.success) {
        gruposHerramientas = data.grupos;
        
        const select = document.getElementById('filtroGrupoHerramientas');
        select.innerHTML = '<option value="">Todos los grupos</option>';
        
        data.grupos.forEach(g => {
          const option = document.createElement('option');
          option.value = g.codigo;
          option.textContent = `${g.codigo} - ${g.nombre}`;
          select.appendChild(option);
        });
      }
    } catch (error) {
      console.error('❌ Error al cargar grupos:', error);
    }
  }

  // ===== CARGAR FRACCIONES =====
  async function cargarFracciones() {
    try {
      const response = await fetch('/api/kits/fracciones-disponibles');
      const data = await response.json();
      
      if (data.success) {
        fraccionesDisponibles = data.fracciones;
        
        const selectModal = document.getElementById('kitFraccion');
        selectModal.innerHTML = '<option value="">Seleccionar fracción...</option>';
        
        data.fracciones.forEach(f => {
          const option = document.createElement('option');
          option.value = f.codigo;
          option.textContent = `${f.codigo} - ${f.nombre}`;
          option.dataset.nombre = f.nombre;
          option.dataset.fraccionId = f.fraccion_id;
          selectModal.appendChild(option);
        });
        
        const selectFiltro = document.getElementById('filtroFraccion');
        selectFiltro.innerHTML = '<option value="">Todas las fracciones</option>';
        
        data.fracciones.forEach(f => {
          const option = document.createElement('option');
          option.value = f.codigo;
          option.textContent = `${f.codigo} - ${f.nombre}`;
          selectFiltro.appendChild(option);
        });
      }
    } catch (error) {
      console.error('❌ Error al cargar fracciones:', error);
    }
  }

  // ===== CARGAR HERRAMIENTAS =====
  async function cargarHerramientas(grupo = '') {
    try {
      const url = grupo ? `/api/kits/herramientas-disponibles?grupo=${grupo}` : '/api/kits/herramientas-disponibles';
      const response = await fetch(url);
      const data = await response.json();
      
      if (data.success) {
        herramientasDisponibles = data.herramientas;
        renderHerramientasCheckboxes();
      }
    } catch (error) {
      console.error('❌ Error al cargar herramientas:', error);
    }
  }

  // ===== RENDERIZAR CHECKBOXES DE HERRAMIENTAS =====
  function renderHerramientasCheckboxes(herramientasSeleccionadas = []) {
    const grid = document.getElementById('herramientasGrid');
    
    if (herramientasDisponibles.length === 0) {
      grid.innerHTML = '<p style="text-align:center;color:#888;padding:20px;">No hay herramientas activas</p>';
      return;
    }
    
    grid.innerHTML = herramientasDisponibles.map(h => {
      const checked = herramientasSeleccionadas.includes(h.herramienta_id) ? 'checked' : '';
      return `
        <label class="herramienta-checkbox">
          <input type="checkbox" 
                 value="${h.herramienta_id}" 
                 name="herramientas" 
                 ${checked}
                 onchange="actualizarContador()">
          <div class="herramienta-info">
            <strong>${h.herramienta_id} ${h.nombre}</strong>
            <small>${h.descripcion}</small>
          </div>
        </label>
      `;
    }).join('');
    
    actualizarContador();
  }

  // ===== ACTUALIZAR CONTADOR =====
  window.actualizarContador = function() {
    const checkboxes = document.querySelectorAll('input[name="herramientas"]:checked');
    const contador = document.getElementById('contadorSeleccion');
    contador.textContent = `${checkboxes.length} herramienta${checkboxes.length !== 1 ? 's' : ''} seleccionada${checkboxes.length !== 1 ? 's' : ''}`;
  };

  // ===== FILTRAR HERRAMIENTAS POR GRUPO =====
  document.getElementById('filtroGrupoHerramientas')?.addEventListener('change', async function() {
    const grupo = this.value;
    await cargarHerramientas(grupo);
  });

  // ===== CARGAR KITS =====
  async function cargarKits() {
    try {
      const response = await fetch('/api/kits?per_page=1000');
      const data = await response.json();
      
      if (data.success) {
        kitsCache = data.kits;
        aplicarFiltros();
      }
    } catch (error) {
      console.error('❌ Error al cargar kits:', error);
      tablaContainer.innerHTML = '<p style="text-align:center;color:#888;">Error al cargar kits</p>';
    }
  }

  // ===== APLICAR FILTROS =====
  function aplicarFiltros() {
    const fraccionFiltro = filtroFraccion.value;
    const nivelFiltro = filtroNivel.value;
    
    let kitsFiltrados = kitsCache;
    
    if (fraccionFiltro) {
      kitsFiltrados = kitsFiltrados.filter(k => k.codigo === fraccionFiltro);
    }
    
    if (nivelFiltro) {
      if (nivelFiltro === 'general') {
        kitsFiltrados = kitsFiltrados.filter(k => k.nivel_limpieza_id === null);
      } else {
        kitsFiltrados = kitsFiltrados.filter(k => k.nivel_limpieza_id === parseInt(nivelFiltro));
      }
    }
    
    renderTabla(kitsFiltrados);
  }
  // ===== RENDERIZAR TABLA =====
  function renderTabla(kits) {
    if (kits.length === 0) {
      tablaContainer.innerHTML = `
        <div class="empty-state">
          <div style="font-size:3rem;margin-bottom:12px;">🧰</div>
          <div style="font-size:1.1rem;margin-bottom:8px;">No hay kits</div>
          <div style="font-size:.9rem;color:#999;">Agrega tu primer kit</div>
        </div>
      `;
      return;
    }
    
    const html = `
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Fracción</th>
            <th>Nombre</th>
            <th>Nivel</th>
            <th>Herramientas</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          ${kits.map(k => `
            <tr>
              <td><code>${k.kit_id}</code></td>
              <td>${k.codigo}</td>
              <td><strong>${k.nombre}</strong></td>
              <td>
                <span class="badge">
                  ${k.nivel_limpieza_id === null ? 'General' : `Nivel ${k.nivel_limpieza_id}`}
                </span>
              </td>
              <td>
                <div class="herramientas-list">
                  ${k.herramientas.slice(0, 3).map(h => `
                    <span class="herramienta-tag" title="${h.nombre}">${h.herramienta_id}</span>
                  `).join('')}
                  ${k.cantidad_herramientas > 3 ? `<span class="herramienta-tag">+${k.cantidad_herramientas - 3}</span>` : ''}
                </div>
              </td>
              <td>
                <div class="actions">
                  <button class="btn-icon btn-editar-kit"
                          data-id="${k.kit_id}"
                          data-nombre="${k.nombre}"
                          data-nivel="${k.nivel_limpieza_id || ''}"
                          data-herramientas='${JSON.stringify(k.herramientas.map(h => h.herramienta_id))}'
                          title="Editar">
                    ✏️
                  </button>
                  <button class="btn-icon btn-delete btn-eliminar-kit"
                          data-id="${k.kit_id}"
                          data-nombre="${k.nombre}"
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

  // ===== AUTO-LLENAR NOMBRE Y ID AL SELECCIONAR FRACCIÓN =====
  document.getElementById('kitFraccion')?.addEventListener('change', async function() {
    const codigo = this.value;
    const nombreFraccion = this.options[this.selectedIndex].dataset.nombre;
    
    if (!codigo) {
      document.getElementById('kitId').value = '';
      document.getElementById('kitNombre').value = '';
      return;
    }
    
    document.getElementById('kitNombre').value = `Kit ${nombreFraccion}`;
    
    try {
      const response = await fetch(`/api/kits/next-id?codigo=${codigo}`);
      const data = await response.json();
      
      if (data.success) {
        document.getElementById('kitId').value = data.kit_id;
      }
    } catch (error) {
      console.error('❌ Error al obtener ID:', error);
    }
  });

  // ===== ABRIR MODAL =====
  async function abrirModal(modo, id = null, nombre = '', nivel = '', herramientasSeleccionadas = []) {
    modoModal = modo;
    kitActualId = id;

    const modal = document.getElementById('modalKit');
    const titulo = document.getElementById('modalKitTitulo');
    const fraccionField = document.getElementById('fraccionField');
    const fraccionSelect = document.getElementById('kitFraccion');
    const idInput = document.getElementById('kitId');
    const nombreInput = document.getElementById('kitNombre');
    const nivelSelect = document.getElementById('kitNivel');

    document.getElementById('formKit').reset();
    idInput.value = '';
    document.getElementById('filtroGrupoHerramientas').value = '';

    if (modo === 'crear') {
      titulo.textContent = 'Agregar Kit';
      fraccionField.style.display = 'block';
      fraccionSelect.setAttribute('required', '');
      
      await cargarHerramientas();
      renderHerramientasCheckboxes([]);

    } else if (modo === 'editar') {
      titulo.textContent = 'Editar Kit';
      fraccionField.style.display = 'none';
      fraccionSelect.removeAttribute('required');
      
      idInput.value = id;
      nombreInput.value = nombre;
      nivelSelect.value = nivel === '' || nivel === null ? 'general' : nivel;
      
      await cargarHerramientas();
      renderHerramientasCheckboxes(herramientasSeleccionadas);
    }

    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }

  // ===== CERRAR MODAL =====
  function cerrarModal() {
    const modal = document.getElementById('modalKit');
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
    
    document.getElementById('formKit').reset();
    document.getElementById('kitId').value = '';
    document.getElementById('fraccionField').style.display = 'block';
    modoModal = 'crear';
    kitActualId = null;
  }

  // ===== GUARDAR KIT =====
  async function guardarKit(event) {
    event.preventDefault();

    const btnGuardar = document.getElementById('btnGuardarKit');
    const herramientasSeleccionadas = Array.from(
      document.querySelectorAll('input[name="herramientas"]:checked')
    ).map(cb => cb.value);

    if (herramientasSeleccionadas.length === 0) {
      alert('Debe seleccionar al menos 1 herramienta');
      return;
    }

    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';

    try {
      let response, data;

      if (modoModal === 'crear') {
        const codigo = document.getElementById('kitFraccion').value;
        const nombre = document.getElementById('kitNombre').value.trim();
        const nivelValue = document.getElementById('kitNivel').value;
        const nivel_limpieza_id = (nivelValue === '' || nivelValue === 'general') ? null : parseInt(nivelValue);

        response = await fetch('/api/kits', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            codigo, 
            nombre, 
            nivel_limpieza_id, 
            herramientas: herramientasSeleccionadas 
          })
        });

      } else if (modoModal === 'editar') {
        const nombre = document.getElementById('kitNombre').value.trim();
        const nivelValue = document.getElementById('kitNivel').value;
        const nivel_limpieza_id = (nivelValue === '' || nivelValue === 'general') ? null : parseInt(nivelValue);

        response = await fetch(`/api/kits/${kitActualId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            nombre, 
            nivel_limpieza_id, 
            herramientas: herramientasSeleccionadas 
          })
        });
      }

      data = await response.json();

      if (data.success) {
        alert(modoModal === 'crear' ? 'Kit creado correctamente' : 'Kit actualizado correctamente');
        cerrarModal();
        await cargarKits();
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

  // ===== ELIMINAR KIT =====
  async function eliminarKit(id, nombre) {
    const confirmar = confirm(
      `¿Estás seguro de eliminar el kit ${id} (${nombre})?\n\n` +
      `Esta acción no se puede deshacer.`
    );

    if (!confirmar) return;

    try {
      const response = await fetch(`/api/kits/${id}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        alert('Kit eliminado correctamente');
        await cargarKits();
      } else {
        alert('Error: ' + data.error);
      }

    } catch (error) {
      console.error('❌ Error:', error);
      alert('Error de conexión');
    }
  }

  // ===== EVENT LISTENERS =====
  document.querySelector('.btn-agregar-kit')?.addEventListener('click', function() {
    abrirModal('crear');
  });

  document.querySelector('.modal-close')?.addEventListener('click', cerrarModal);
  document.querySelector('.modal-overlay')?.addEventListener('click', cerrarModal);
  document.querySelector('.btn-cancel-kit')?.addEventListener('click', cerrarModal);

  document.getElementById('formKit')?.addEventListener('submit', guardarKit);

  document.addEventListener('click', function(e) {
    if (e.target.closest('.btn-editar-kit')) {
      const btn = e.target.closest('.btn-editar-kit');
      const herramientas = JSON.parse(btn.dataset.herramientas);
      abrirModal('editar', btn.dataset.id, btn.dataset.nombre, btn.dataset.nivel, herramientas);
    }

    if (e.target.closest('.btn-eliminar-kit')) {
      const btn = e.target.closest('.btn-eliminar-kit');
      eliminarKit(btn.dataset.id, btn.dataset.nombre);
    }
  });

  init();

})();