// ===== KITS EVENTOS - CRUD COMPLETO =====
(function() {
  'use strict';

  let modoModal = 'crear';
  let kitActualId = null;
  let eventosDisponibles = [];
  let casosDisponibles = [];
  let herramientasDisponibles = [];
  let gruposHerramientas = [];
  let kitsCache = [];
  let herramientasSeleccionadas = new Set();
  
  const filtroEvento = document.getElementById('filtroEvento');
  const filtroCaso = document.getElementById('filtroCaso');
  const tablaContainer = document.getElementById('tablaContainer');

  // ===== INICIALIZAR =====
  async function init() {
    await cargarGruposHerramientas();
    await cargarEventos();
    await cargarKits();
    
    filtroEvento?.addEventListener('change', async function() {
      await cargarCasosPorEvento(this.value);
      aplicarFiltros();
    });
    
    filtroCaso?.addEventListener('change', aplicarFiltros);
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

  // ===== CARGAR EVENTOS =====
  async function cargarEventos() {
    try {
      const response = await fetch('/api/kits-eventos/eventos-disponibles');
      const data = await response.json();
      
      if (data.success) {
        eventosDisponibles = data.eventos;
        
        // Poblar dropdown modal
        const selectModal = document.getElementById('kitEvento');
        selectModal.innerHTML = '<option value="">Seleccionar evento...</option>';
        
        data.eventos.forEach(e => {
          const option = document.createElement('option');
          option.value = e.evento_tipo_id;
          option.textContent = `${e.evento_tipo_id} - ${e.nombre}`;
          selectModal.appendChild(option);
        });
        
        // Poblar filtro
        const selectFiltro = document.getElementById('filtroEvento');
        selectFiltro.innerHTML = '<option value="">Todos los eventos</option>';
        
        data.eventos.forEach(e => {
          const option = document.createElement('option');
          option.value = e.evento_tipo_id;
          option.textContent = `${e.evento_tipo_id} - ${e.nombre}`;
          selectFiltro.appendChild(option);
        });
      }
    } catch (error) {
      console.error('❌ Error al cargar eventos:', error);
    }
  }

  // ===== CARGAR CASOS (por evento o todos) =====
  async function cargarCasosPorEvento(eventoId = '') {
    try {
      const url = eventoId 
        ? `/api/kits-eventos/casos-disponibles?evento_tipo=${eventoId}`
        : '/api/kits-eventos/casos-disponibles';
      
      const response = await fetch(url);
      const data = await response.json();
      
      if (data.success) {
        casosDisponibles = data.casos;
        
        // Poblar dropdown modal
        const selectModal = document.getElementById('kitCaso');
        selectModal.innerHTML = '<option value="">Seleccionar caso...</option>';
        
        data.casos.forEach(c => {
          const option = document.createElement('option');
          option.value = c.caso_id;
          option.textContent = `${c.caso_id} - ${c.nombre}`;
          option.dataset.nombre = c.nombre;
          selectModal.appendChild(option);
        });
        
        // Poblar filtro
        const selectFiltro = document.getElementById('filtroCaso');
        selectFiltro.innerHTML = '<option value="">Todos los casos</option>';
        
        data.casos.forEach(c => {
          const option = document.createElement('option');
          option.value = c.caso_id;
          option.textContent = `${c.caso_id} - ${c.nombre}`;
          selectFiltro.appendChild(option);
        });
      }
    } catch (error) {
      console.error('❌ Error al cargar casos:', error);
    }
  }

  // ===== CARGAR HERRAMIENTAS =====
  async function cargarHerramientas(grupo = '') {
    try {
      const url = grupo 
        ? `/api/kits/herramientas-disponibles?grupo=${grupo}` 
        : '/api/kits/herramientas-disponibles';
      
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
  function renderHerramientasCheckboxes() {
    const grid = document.getElementById('herramientasGrid');
    
    if (herramientasDisponibles.length === 0) {
      grid.innerHTML = '<p style="text-align:center;color:#888;padding:20px;">No hay herramientas activas</p>';
      actualizarContador();
      return;
    }
    
    let html = '';
    
    herramientasDisponibles.forEach(h => {
      const isChecked = herramientasSeleccionadas.has(h.herramienta_id);
      
      html += `
        <label class="herramienta-checkbox">
          <input 
            type="checkbox" 
            value="${h.herramienta_id}"
            name="herramientas"
            ${isChecked ? 'checked' : ''}
          >
          <div class="herramienta-info">
            <strong>${h.herramienta_id} ${h.nombre}</strong>
            <small>${h.descripcion}</small>
          </div>
        </label>
      `;
    });
    
    grid.innerHTML = html;
    
    grid.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
      checkbox.addEventListener('change', function() {
        if (this.checked) {
          herramientasSeleccionadas.add(this.value);
        } else {
          herramientasSeleccionadas.delete(this.value);
        }
        actualizarContador();
      });
    });
    
    actualizarContador();
  }

  // ===== ACTUALIZAR CONTADOR =====
  function actualizarContador() {
    const contador = document.getElementById('contadorSeleccion');
    const count = herramientasSeleccionadas.size;
    
    if (contador) {
      contador.textContent = `${count} herramienta${count !== 1 ? 's' : ''} seleccionada${count !== 1 ? 's' : ''}`;
    }
  }

  // ===== FILTRAR HERRAMIENTAS POR GRUPO =====
  document.getElementById('filtroGrupoHerramientas')?.addEventListener('change', async function() {
    const grupo = this.value;
    await cargarHerramientas(grupo);
  });

  // ===== CARGAR KITS =====
  async function cargarKits() {
    try {
      const response = await fetch('/api/kits-eventos?per_page=1000');
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
    const eventoSeleccionado = filtroEvento?.value || '';
    const casoSeleccionado = filtroCaso?.value || '';
    
    let kitsFiltrados = kitsCache;
    
    if (eventoSeleccionado) {
      kitsFiltrados = kitsFiltrados.filter(k => k.evento_tipo_id === eventoSeleccionado);
    }
    
    if (casoSeleccionado) {
      kitsFiltrados = kitsFiltrados.filter(k => k.caso_id === casoSeleccionado);
    }
    
    renderTabla(kitsFiltrados);
  }

  // ===== RENDERIZAR TABLA =====
  function renderTabla(kits) {
    if (kits.length === 0) {
      tablaContainer.innerHTML = `
        <div class="empty-state">
          <div style="font-size:3rem;margin-bottom:1rem;">🧰</div>
          <div style="font-size:1.1rem;font-weight:600;margin-bottom:.5rem;">No hay kits de eventos</div>
          <div>Crea tu primer kit usando el botón "Agregar Kit"</div>
        </div>
      `;
      return;
    }
    
    const html = `
      <table>
        <thead>
          <tr>
            <th>Kit ID</th>
            <th>Evento</th>
            <th>Caso</th>
            <th>Nombre</th>
            <th>Herramientas</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          ${kits.map(k => `
            <tr>
              <td><strong>${k.kit_id}</strong></td>
              <td>${k.evento_nombre}</td>
              <td>${k.caso_nombre}</td>
              <td>${k.nombre}</td>
              <td>
                <span class="badge">${k.cantidad_herramientas} herramienta${k.cantidad_herramientas !== 1 ? 's' : ''}</span>
              </td>
              <td>
                <div class="actions">
                  <button 
                    class="btn-icon btn-editar-kit" 
                    title="Editar"
                    data-id="${k.kit_id}"
                    data-nombre="${k.nombre}"
                    data-caso="${k.caso_id}"
                    data-herramientas='${JSON.stringify(k.herramientas.map(h => h.herramienta_id))}'
                  >
                    ✏️
                  </button>
                  <button 
                    class="btn-icon btn-delete btn-eliminar-kit" 
                    title="Eliminar"
                    data-id="${k.kit_id}"
                    data-nombre="${k.nombre}"
                  >
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

  // ===== AUTO-LLENAR NOMBRE Y ID AL SELECCIONAR CASO =====
  document.getElementById('kitCaso')?.addEventListener('change', async function() {
    const casoId = this.value;
    const nombreCaso = this.options[this.selectedIndex].dataset.nombre;
    
    if (!casoId) {
      document.getElementById('kitId').value = '';
      document.getElementById('kitNombre').value = '';
      return;
    }
    
    document.getElementById('kitNombre').value = `Kit ${nombreCaso}`;
    
    try {
      const response = await fetch(`/api/kits-eventos/next-id?caso_id=${casoId}`);
      const data = await response.json();
      
      if (data.success) {
        document.getElementById('kitId').value = data.kit_id;
      }
    } catch (error) {
      console.error('❌ Error al obtener ID:', error);
    }
  });

  // ===== AUTO-CARGAR CASOS AL SELECCIONAR EVENTO EN MODAL =====
  document.getElementById('kitEvento')?.addEventListener('change', async function() {
    const eventoId = this.value;
    
    if (!eventoId) {
      document.getElementById('kitCaso').innerHTML = '<option value="">Seleccionar caso...</option>';
      document.getElementById('kitId').value = '';
      document.getElementById('kitNombre').value = '';
      return;
    }
    
    await cargarCasosPorEvento(eventoId);
  });

  // ===== ABRIR MODAL =====
  async function abrirModal(modo, id = null, nombre = '', casoId = '', herramientasExistentes = []) {
    modoModal = modo;
    kitActualId = id;

    const modal = document.getElementById('modalKit');
    const titulo = document.getElementById('modalKitTitulo');
    const eventoSelect = document.getElementById('kitEvento');
    const casoSelect = document.getElementById('kitCaso');
    const idInput = document.getElementById('kitId');
    const nombreInput = document.getElementById('kitNombre');

    document.getElementById('formKit').reset();
    idInput.value = '';
    document.getElementById('filtroGrupoHerramientas').value = '';

    herramientasSeleccionadas.clear();
    
    if (modo === 'crear') {
      titulo.textContent = 'Agregar Kit de Evento';
      
      // Pre-seleccionar filtros si existen
      const filtroEventoVal = filtroEvento?.value || '';
      const filtroCasoVal = filtroCaso?.value || '';
      
      if (filtroEventoVal) {
        eventoSelect.value = filtroEventoVal;
        await cargarCasosPorEvento(filtroEventoVal);
        
        if (filtroCasoVal) {
          casoSelect.value = filtroCasoVal;
          // Trigger change para auto-llenar nombre e ID
          casoSelect.dispatchEvent(new Event('change'));
        }
      }

    } else if (modo === 'editar') {
      titulo.textContent = 'Editar Kit de Evento';
      
      // Ocultar selects de evento/caso en modo edición
      eventoSelect.disabled = true;
      casoSelect.disabled = true;
      
      idInput.value = id;
      nombreInput.value = nombre;
      
      // Cargar caso del kit
      const kit = kitsCache.find(k => k.kit_id === id);
      if (kit) {
        eventoSelect.value = kit.evento_tipo_id;
        await cargarCasosPorEvento(kit.evento_tipo_id);
        casoSelect.value = casoId;
      }
      
      herramientasExistentes.forEach(hid => herramientasSeleccionadas.add(hid));
    }
    
    await cargarHerramientas();

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
    document.getElementById('kitEvento').disabled = false;
    document.getElementById('kitCaso').disabled = false;
    
    herramientasSeleccionadas.clear();
    
    modoModal = 'crear';
    kitActualId = null;
  }

  // ===== GUARDAR KIT =====
  async function guardarKit(event) {
    event.preventDefault();

    const btnGuardar = document.getElementById('btnGuardarKit');
    
    const herramientasArray = Array.from(herramientasSeleccionadas);

    if (herramientasArray.length === 0) {
      alert('Debe seleccionar al menos 1 herramienta');
      return;
    }

    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';

    try {
      let response, data;

      if (modoModal === 'crear') {
        const casoId = document.getElementById('kitCaso').value;
        const nombre = document.getElementById('kitNombre').value.trim();

        if (!casoId) {
          alert('Debe seleccionar un caso');
          btnGuardar.disabled = false;
          btnGuardar.textContent = 'Guardar';
          return;
        }

        response = await fetch('/api/kits-eventos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            caso_id: casoId,
            nombre, 
            herramientas: herramientasArray
          })
        });

      } else if (modoModal === 'editar') {
        const nombre = document.getElementById('kitNombre').value.trim();

        response = await fetch(`/api/kits-eventos/${kitActualId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            nombre, 
            herramientas: herramientasArray
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
      const response = await fetch(`/api/kits-eventos/${id}`, {
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
      abrirModal('editar', btn.dataset.id, btn.dataset.nombre, btn.dataset.caso, herramientas);
    }

    if (e.target.closest('.btn-eliminar-kit')) {
      const btn = e.target.closest('.btn-eliminar-kit');
      eliminarKit(btn.dataset.id, btn.dataset.nombre);
    }
  });

  init();

})();