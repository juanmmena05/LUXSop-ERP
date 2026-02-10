// ===== FRACCIONES EVENTOS - CRUD COMPLETO =====
(function() {
  'use strict';

  let modoModal = 'crear';
  let fraccionActualId = null;
  let eventosDisponibles = [];
  let codigosDisponibles = [];
  let fraccionesCache = [];
  
  const filtroEvento = document.getElementById('filtroEvento');
  const tablaContainer = document.getElementById('tablaContainer');

  // ===== INICIALIZAR =====
  async function init() {
    await cargarEventos();
    await cargarFracciones();
    
    filtroEvento?.addEventListener('change', aplicarFiltros);
  }

  // ===== CARGAR EVENTOS =====
  async function cargarEventos() {
    try {
      const response = await fetch('/api/fracciones-eventos/eventos-disponibles');
      const data = await response.json();
      
      if (data.success) {
        eventosDisponibles = data.eventos;
        
        // Poblar dropdown modal
        const selectModal = document.getElementById('fraccionEvento');
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

  // ===== CARGAR CÓDIGOS DISPONIBLES POR EVENTO =====
  async function cargarCodigosPorEvento(eventoId) {
    try {
      if (!eventoId) {
        document.getElementById('fraccionCodigo').innerHTML = '<option value="">Seleccionar código...</option>';
        document.getElementById('fraccionCodigo').disabled = true;
        document.getElementById('alertaSinCodigos').style.display = 'none';
        return;
      }
      
      const response = await fetch(`/api/fracciones-eventos/codigos-disponibles?evento_tipo=${eventoId}`);
      const data = await response.json();
      
      if (data.success) {
        codigosDisponibles = data.codigos;
        
        const selectCodigo = document.getElementById('fraccionCodigo');
        selectCodigo.innerHTML = '<option value="">Seleccionar código...</option>';
        
        if (data.codigos.length === 0) {
          // No hay códigos disponibles
          selectCodigo.disabled = true;
          document.getElementById('alertaSinCodigos').style.display = 'block';
          document.getElementById('fraccionId').value = '';
        } else {
          // Hay códigos disponibles
          selectCodigo.disabled = false;
          document.getElementById('alertaSinCodigos').style.display = 'none';
          
          data.codigos.forEach(c => {
            const option = document.createElement('option');
            option.value = c.codigo;
            option.textContent = `${c.codigo} - ${c.nombre_base}`;
            option.dataset.count = c.count;
            option.dataset.nombreBase = c.nombre_base;
            selectCodigo.appendChild(option);
          });
        }
      }
    } catch (error) {
      console.error('❌ Error al cargar códigos:', error);
    }
  }

  // ===== AUTO-GENERAR ID AL SELECCIONAR CÓDIGO =====
  // ===== AUTO-GENERAR ID Y MANEJAR CAMPOS DE NOMBRE AL SELECCIONAR CÓDIGO =====
document.getElementById('fraccionCodigo')?.addEventListener('change', async function() {
  const eventoId = document.getElementById('fraccionEvento').value;
  const codigo = this.value;
  
  const groupNombreBase = document.getElementById('groupNombreBase');
  const groupNombreCustom = document.getElementById('groupNombreCustom');
  const groupNombreCompleto = document.getElementById('groupNombreCompleto');
  const inputNombreBase = document.getElementById('fraccionNombreBase');
  const inputNombreCustom = document.getElementById('fraccionNombreCustom');
  const inputNombreCompleto = document.getElementById('fraccionNombre');
  
  if (!eventoId || !codigo) {
    document.getElementById('fraccionId').value = '';
    // Resetear a modo nombre completo
    groupNombreBase.style.display = 'none';
    groupNombreCustom.style.display = 'none';
    groupNombreCompleto.style.display = 'block';
    inputNombreCustom.required = false;
    inputNombreCompleto.required = true;
    return;
  }
  
  // Obtener datos del option seleccionado
  const selectedOption = this.options[this.selectedIndex];
  const count = parseInt(selectedOption.dataset.count || 0);
  const nombreBase = selectedOption.dataset.nombreBase || '';
  
  try {
    const response = await fetch(`/api/fracciones-eventos/next-id?evento_tipo=${eventoId}&codigo=${codigo}`);
    const data = await response.json();
    
    if (data.success) {
      document.getElementById('fraccionId').value = data.fraccion_evento_id;
      
      // Si ya existen fracciones con este código (count > 0)
      if (count > 0) {
        // Modo: Nombre Base (readonly) + Custom (obligatorio)
        inputNombreBase.value = nombreBase;
        inputNombreCustom.value = '';
        
        groupNombreBase.style.display = 'block';
        groupNombreCustom.style.display = 'block';
        groupNombreCompleto.style.display = 'none';
        
        inputNombreCustom.required = true;
        inputNombreCompleto.required = false;
      } else {
        // Modo: Nombre Completo (libre)
        inputNombreCompleto.value = '';
        
        groupNombreBase.style.display = 'none';
        groupNombreCustom.style.display = 'none';
        groupNombreCompleto.style.display = 'block';
        
        inputNombreCustom.required = false;
        inputNombreCompleto.required = true;
      }
    }
  } catch (error) {
    console.error('❌ Error al obtener ID:', error);
  }
});

  // ===== CARGAR CÓDIGOS AL SELECCIONAR EVENTO EN MODAL =====
  document.getElementById('fraccionEvento')?.addEventListener('change', async function() {
    const eventoId = this.value;
    
    // Limpiar campos dependientes
    document.getElementById('fraccionCodigo').innerHTML = '<option value="">Seleccionar código...</option>';
    document.getElementById('fraccionId').value = '';
    
    if (!eventoId) {
      document.getElementById('fraccionCodigo').disabled = true;
      document.getElementById('alertaSinCodigos').style.display = 'none';
      return;
    }
    
    await cargarCodigosPorEvento(eventoId);
  });

  // ===== CARGAR FRACCIONES =====
  async function cargarFracciones() {
    try {
      const response = await fetch('/api/fracciones-eventos?per_page=1000');
      const data = await response.json();
      
      if (data.success) {
        fraccionesCache = data.fracciones;
        aplicarFiltros();
      }
    } catch (error) {
      console.error('❌ Error al cargar fracciones:', error);
      tablaContainer.innerHTML = '<p style="text-align:center;color:#888;">Error al cargar fracciones</p>';
    }
  }

  // ===== APLICAR FILTROS =====
  function aplicarFiltros() {
    const eventoSeleccionado = filtroEvento?.value || '';
    
    let fraccionesFiltradas = fraccionesCache;
    
    if (eventoSeleccionado) {
      fraccionesFiltradas = fraccionesFiltradas.filter(f => f.evento_tipo_id === eventoSeleccionado);
    }
    
    renderTabla(fraccionesFiltradas);
  }

  // ===== RENDERIZAR TABLA =====
  function renderTabla(fracciones) {
    if (fracciones.length === 0) {
      tablaContainer.innerHTML = `
        <div class="empty-state">
          <div style="font-size:3rem;margin-bottom:1rem;">📊</div>
          <div style="font-size:1.1rem;font-weight:600;margin-bottom:.5rem;">No hay fracciones de eventos</div>
          <div>Crea tu primera fracción usando el botón "Agregar Fracción"</div>
        </div>
      `;
      return;
    }
    
    const html = `
      <table>
        <thead>
          <tr>
            <th>Fracción ID</th>
            <th>Evento</th>
            <th>Código</th>
            <th>Nombre</th>
            <th>Metodología</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>
          ${fracciones.map(f => {
            let metodologiaBadge = '';
            
            if (f.tiene_metodologia) {
              if (f.cantidad_pasos > 0) {
                metodologiaBadge = `<span class="badge badge-success">✅ ${f.cantidad_pasos} paso${f.cantidad_pasos !== 1 ? 's' : ''}</span>`;
              } else {
                metodologiaBadge = `<span class="badge badge-warning">⚠️ Sin pasos</span>`;
              }
            } else {
              metodologiaBadge = `<span class="badge badge-warning">❌ Sin metodología</span>`;
            }
            
            return `
              <tr>
                <td><strong>${f.fraccion_evento_id}</strong></td>
                <td>${f.evento_nombre}</td>
                <td><span class="badge">${f.codigo}</span></td>
                <td>${f.nombre}</td>
                <td>${metodologiaBadge}</td>
                <td>
                  <div class="actions">
                    <button 
                      class="btn-icon btn-metodologia" 
                      title="Editar Metodología"
                      onclick="location.href='/catalogos/metodologias-eventos/${f.metodologia_id || ''}'"
                    >
                      🔧
                    </button>
                    <button 
                      class="btn-icon btn-editar-fraccion" 
                      title="Editar Fracción"
                      data-id="${f.fraccion_evento_id}"
                      data-nombre="${f.nombre}"
                      data-descripcion="${f.descripcion || ''}"
                      data-evento="${f.evento_tipo_id}"
                    >
                      ✏️
                    </button>
                    <button 
                      class="btn-icon btn-delete btn-eliminar-fraccion" 
                      title="Eliminar Fracción"
                      data-id="${f.fraccion_evento_id}"
                      data-nombre="${f.nombre}"
                    >
                      🗑️
                    </button>
                  </div>
                </td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    `;
    
    tablaContainer.innerHTML = html;
  }

  // ===== ABRIR MODAL =====
  async function abrirModal(modo, id = null, nombre = '', descripcion = '', eventoId = '') {
    modoModal = modo;
    fraccionActualId = id;

    const modal = document.getElementById('modalFraccion');
    const titulo = document.getElementById('modalFraccionTitulo');
    const eventoSelect = document.getElementById('fraccionEvento');
    const codigoSelect = document.getElementById('fraccionCodigo');
    const idInput = document.getElementById('fraccionId');
    const nombreInput = document.getElementById('fraccionNombre');
    const descripcionInput = document.getElementById('fraccionDescripcion');

    document.getElementById('formFraccion').reset();
    idInput.value = '';
    codigoSelect.innerHTML = '<option value="">Seleccionar código...</option>';
    codigoSelect.disabled = true;
    document.getElementById('alertaSinCodigos').style.display = 'none';
    
    if (modo === 'crear') {
      titulo.textContent = 'Agregar Fracción de Evento';
      
      eventoSelect.disabled = false;
      codigoSelect.disabled = false;
      
      // Pre-seleccionar evento del filtro si existe
      const filtroEventoVal = filtroEvento?.value || '';
      if (filtroEventoVal) {
        eventoSelect.value = filtroEventoVal;
        await cargarCodigosPorEvento(filtroEventoVal);
      }

    } else if (modo === 'editar') {
      titulo.textContent = 'Editar Fracción de Evento';
      
      // Deshabilitar selects de evento y código
      eventoSelect.disabled = true;
      codigoSelect.disabled = true;
      
      idInput.value = id;
      nombreInput.value = nombre;
      descripcionInput.value = descripcion;
      
      // Mostrar evento (solo lectura)
      eventoSelect.value = eventoId;
      
      // Extraer y mostrar código
      const partes = id.split('-');
      if (partes.length >= 3) {
        const codigo = partes[2];
        codigoSelect.innerHTML = `<option value="${codigo}">${codigo}</option>`;
        codigoSelect.value = codigo;
      }
    }

    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }

  // ===== CERRAR MODAL =====
  function cerrarModal() {
    const modal = document.getElementById('modalFraccion');
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
    
    document.getElementById('formFraccion').reset();
    document.getElementById('fraccionId').value = '';
    document.getElementById('fraccionEvento').disabled = false;
    document.getElementById('fraccionCodigo').disabled = false;
    document.getElementById('alertaSinCodigos').style.display = 'none';
    
    modoModal = 'crear';
    fraccionActualId = null;
  }

  // ===== GUARDAR FRACCIÓN =====
  async function guardarFraccion(event) {
    event.preventDefault();

    const btnGuardar = document.getElementById('btnGuardarFraccion');
    
    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';

    try {
      let response, data;

      if (modoModal === 'crear') {
        const eventoId = document.getElementById('fraccionEvento').value;
        const codigo = document.getElementById('fraccionCodigo').value;

        // Determinar si usamos nombre completo o nombre base + custom
        const groupNombreCompleto = document.getElementById('groupNombreCompleto');
        const isNombreCompleto = groupNombreCompleto.style.display !== 'none';

        let nombre;
        if (isNombreCompleto) {
          // Primera fracción: nombre completo
          nombre = document.getElementById('fraccionNombre').value.trim();
          
          if (!nombre) {
            alert('⚠️ Debe ingresar un nombre para la fracción');
            btnGuardar.disabled = false;
            btnGuardar.textContent = 'Guardar';
            return;
          }
        } else {
          // Fracción 002+: nombre base + custom
          const nombreBase = document.getElementById('fraccionNombreBase').value.trim();
          const nombreCustom = document.getElementById('fraccionNombreCustom').value.trim();
          
          if (!nombreCustom) {
            alert('⚠️ Debe agregar una variante/custom para diferenciar esta fracción');
            btnGuardar.disabled = false;
            btnGuardar.textContent = 'Guardar';
            return;
          }
          
          nombre = `${nombreBase} — ${nombreCustom}`;
        }
        
        const descripcion = document.getElementById('fraccionDescripcion').value.trim();

        if (!eventoId || !codigo) {
          alert('Debe seleccionar evento y código');
          btnGuardar.disabled = false;
          btnGuardar.textContent = 'Guardar';
          return;
        }

        response = await fetch('/api/fracciones-eventos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            evento_tipo_id: eventoId,
            codigo: codigo,
            nombre,
            descripcion
          })
        });

      } else if (modoModal === 'editar') {
        const nombre = document.getElementById('fraccionNombre').value.trim();
        const descripcion = document.getElementById('fraccionDescripcion').value.trim();

        response = await fetch(`/api/fracciones-eventos/${fraccionActualId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            nombre,
            descripcion
          })
        });
      }

      data = await response.json();

      if (data.success) {
        alert(modoModal === 'crear' ? 'Fracción creada correctamente' : 'Fracción actualizada correctamente');
        cerrarModal();
        await cargarFracciones();
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

  // ===== ELIMINAR FRACCIÓN =====
  async function eliminarFraccion(id, nombre) {
    const confirmar = confirm(
      `¿Estás seguro de eliminar la fracción ${id} (${nombre})?\n\n` +
      `ADVERTENCIA: También se eliminará la metodología asociada.\n` +
      `Esta acción no se puede deshacer.`
    );

    if (!confirmar) return;

    try {
      const response = await fetch(`/api/fracciones-eventos/${id}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        alert('Fracción eliminada correctamente');
        await cargarFracciones();
      } else {
        alert('Error: ' + data.error);
      }

    } catch (error) {
      console.error('❌ Error:', error);
      alert('Error de conexión');
    }
  }

  // ===== EVENT LISTENERS =====
  document.querySelector('.btn-agregar-fraccion')?.addEventListener('click', function() {
    abrirModal('crear');
  });

  document.querySelector('.modal-close')?.addEventListener('click', cerrarModal);
  document.querySelector('.modal-overlay')?.addEventListener('click', cerrarModal);
  document.querySelector('.btn-cancel-fraccion')?.addEventListener('click', cerrarModal);

  document.getElementById('formFraccion')?.addEventListener('submit', guardarFraccion);

  document.addEventListener('click', function(e) {
    if (e.target.closest('.btn-editar-fraccion')) {
      const btn = e.target.closest('.btn-editar-fraccion');
      abrirModal('editar', btn.dataset.id, btn.dataset.nombre, btn.dataset.descripcion, btn.dataset.evento);
    }

    if (e.target.closest('.btn-eliminar-fraccion')) {
      const btn = e.target.closest('.btn-eliminar-fraccion');
      eliminarFraccion(btn.dataset.id, btn.dataset.nombre);
    }
  });

  init();

})();