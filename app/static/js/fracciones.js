// ===== FRACCIONES - CRUD COMPLETO =====
(function() {
  'use strict';

  let fraccionesCache = [];
  let glosarioFracciones = [];
  let esPrimera = true;
  let customsExistentes = [];
  let nombreBase = '';
  let modoModal = 'crear';  // ← AGREGAR esta línea
  let fraccionActualId = null;  // ← AGREGAR esta línea

  
  const filtroGrupo = document.getElementById('filtroGrupo');
  const tablaContainer = document.getElementById('tablaContainer');

  // ===== INICIALIZAR =====
  async function init() {
    await cargarGlosario();
    await cargarFracciones();
    
    // Event listeners de filtros
    filtroGrupo?.addEventListener('change', aplicarFiltros);
  }

  // ===== CARGAR GLOSARIO =====
  async function cargarGlosario() {
    try {
      const response = await fetch('/api/fracciones/catalogos');
      const data = await response.json();
      
      if (data.success) {
        glosarioFracciones = data.grupos;
        
        // Poblar dropdown del modal
        const selectModal = document.getElementById('fraccionCodigo');
        selectModal.innerHTML = '<option value="">Seleccionar código...</option>';
        
        data.grupos.forEach(g => {
          const option = document.createElement('option');
          option.value = g.codigo;
          option.textContent = `${g.codigo} - ${g.nombre}`;
          option.dataset.nombre = g.nombre;
          selectModal.appendChild(option);
        });
      }
    } catch (error) {
      console.error('❌ Error al cargar glosario:', error);
    }
  }

  // ===== CARGAR FRACCIONES =====
  async function cargarFracciones() {
    try {
      const response = await fetch('/api/fracciones?per_page=1000');
      const data = await response.json();
      
      if (data.success) {
        fraccionesCache = data.fracciones;
        aplicarFiltros();
      } else {
        mostrarError('Error al cargar fracciones');
      }
    } catch (error) {
      console.error('❌ Error al cargar fracciones:', error);
      mostrarError('Error de conexión');
    }
  }

  // ===== APLICAR FILTROS =====
  function aplicarFiltros() {
    const grupoFiltro = filtroGrupo.value;
    
    let fraccionesFiltradas = fraccionesCache;
    
    if (grupoFiltro) {
      fraccionesFiltradas = fraccionesFiltradas.filter(f => f.grupo_fracciones === grupoFiltro);
    }
    
    renderTabla(fraccionesFiltradas);
  }

  // ===== RENDERIZAR TABLA =====
  // ===== RENDERIZAR TABLA =====
  function renderTabla(fracciones) {
    if (fracciones.length === 0) {
        tablaContainer.innerHTML = `
        <div class="empty-state">
            <div style="font-size:3rem;margin-bottom:12px;">📊</div>
            <div style="font-size:1.1rem;margin-bottom:8px;">No hay fracciones</div>
            <div style="font-size:.9rem;color:#999;">Agrega tu primera fracción</div>
        </div>
        `;
        return;
    }
    
    const html = `
        <table>
        <thead>
            <tr>
            <th>ID</th>
            <th>Nombre Base</th>
            <th>Nombre Custom</th>
            <th>Niveles</th>
            <th>Grupo</th>
            <th>Acciones</th>
            </tr>
        </thead>
        <tbody>
            ${fracciones.map(f => `
            <tr>
                <td><code>${f.fraccion_id}</code></td>
                <td><strong>${f.fraccion_nombre}</strong></td>
                <td>${f.nombre_custom || '<span style="color:#999;">—</span>'}</td>
                <td>${renderNiveles(f.niveles)}</td>
                <td>
                <span class="badge badge-${f.grupo_fracciones === 'administracion' ? 'admin' : 'prod'}">
                    ${f.grupo_fracciones === 'administracion' ? 'Administración' : 'Producción'}
                </span>
                </td>
                <td>
                <div class="actions">
                    <button class="btn-icon btn-metodologias"
                            data-id="${f.fraccion_id}"
                            title="Configurar Metodologías"
                            style="background: #e3f2fd; border-color: #90caf9; color: #1976d2;">
                    🔧
                    </button>
                    <button class="btn-icon btn-editar-fraccion"
                            data-id="${f.fraccion_id}"
                            title="Editar">
                    ✏️
                    </button>
                    <button class="btn-icon btn-delete btn-eliminar-fraccion"
                            data-id="${f.fraccion_id}"
                            data-nombre="${f.fraccion_nombre}"
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

  // ===== RENDERIZAR NIVELES (BADGES) =====
  function renderNiveles(niveles) {
    const todosLosNiveles = [1, 2, 3, 4];
    const nivel_map = {1: 'B', 2: 'M', 3: 'P', 4: 'E'};
    
    return todosLosNiveles.map(n => {
      const tiene = niveles.includes(n);
      const letra = nivel_map[n];
      const clase = tiene ? 'nivel-badge' : 'nivel-badge nivel-faltante';
      return `<span class="${clase}">${letra}</span>`;
    }).join('');
  }

  // ===== MOSTRAR ERROR =====
  function mostrarError(mensaje) {
    tablaContainer.innerHTML = `
      <div class="empty-state">
        <div style="font-size:3rem;margin-bottom:12px;">❌</div>
        <div style="font-size:1.1rem;margin-bottom:8px;">${mensaje}</div>
        <div style="font-size:.9rem;color:#999;">Intenta recargar la página</div>
      </div>
    `;
  }

  // ===== GENERAR ID AL SELECCIONAR CÓDIGO =====
  document.getElementById('fraccionCodigo')?.addEventListener('change', async function() {
    const codigo = this.value;
    const option = this.options[this.selectedIndex];
    nombreBase = option.dataset.nombre || '';
    
    if (!codigo) {
      document.getElementById('fraccionId').value = '';
      document.getElementById('fraccionCustom').value = '';
      document.getElementById('previewNombre').textContent = '—';
      return;
    }
    
    try {
      const response = await fetch(`/api/fracciones/next-id?codigo=${codigo}`);
      const data = await response.json();
      
      if (data.success) {
        document.getElementById('fraccionId').value = data.fraccion_id;
        esPrimera = data.es_primera;
        customsExistentes = data.customs_existentes || [];
        
        // ✅ Configurar campo custom según es_primera
        const customField = document.getElementById('fraccionCustom');
        const customLabel = document.getElementById('customLabel');
        const customHint = document.getElementById('customHint');
        
        if (esPrimera) {
          // FR-XX-001: Custom NO permitido
          customLabel.textContent = '3. Nombre Custom (No permitido para FR-001)';
          customField.value = '';
          customField.disabled = true;
          customField.required = false;
          customField.style.background = '#f5f5f5';
          customField.style.cursor = 'not-allowed';
          customHint.textContent = 'ℹ️ Primera fracción de este código (usa nombre base sin custom)';
          customHint.style.color = '#0d6efd';
        } else {
          // FR-XX-002+: Custom OBLIGATORIO
          customLabel.innerHTML = '3. Nombre Custom * <span style="color:#dc3545;font-weight:600;">⚠️ Requerido</span>';
          customField.disabled = false;
          customField.required = true;
          customField.style.background = '#fff';
          customField.style.cursor = 'text';
          customHint.textContent = `⚠️ Requerido: ya existe ${data.fraccion_id.replace(/\d{3}$/, '001')}. Debe ser diferente al nombre base`;
          customHint.style.color = '#dc3545';
          
          // Focus en custom
          setTimeout(() => customField.focus(), 100);
        }
        
        // Actualizar preview
        actualizarPreview();
      }
    } catch (error) {
      console.error('❌ Error al obtener ID:', error);
    }
  });

  // ===== ACTUALIZAR PREVIEW EN TIEMPO REAL =====
  document.getElementById('fraccionCustom')?.addEventListener('input', actualizarPreview);

  function actualizarPreview() {
    const custom = document.getElementById('fraccionCustom').value.trim();
    const preview = document.getElementById('previewNombre');
    
    if (!nombreBase) {
      preview.textContent = '—';
      return;
    }
    
    if (esPrimera || !custom) {
      preview.textContent = nombreBase;
    } else {
      preview.textContent = `${nombreBase} — ${custom}`;
    }
  }

  // ===== ABRIR MODAL =====
  function abrirModal() {
    const modal = document.getElementById('modalFraccion');
    document.getElementById('formFraccion').reset();
    document.getElementById('fraccionId').value = '';
    document.getElementById('previewNombre').textContent = '—';
    
    // Reset campo custom
    const customField = document.getElementById('fraccionCustom');
    const customLabel = document.getElementById('customLabel');
    const customHint = document.getElementById('customHint');
    
    customLabel.textContent = '3. Nombre Custom';
    customField.disabled = false;
    customField.required = false;
    customField.style.background = '#fff';
    customField.style.cursor = 'text';
    customHint.textContent = 'Nombre personalizado para esta variación';
    customHint.style.color = '#888';
    
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }

  // ===== ABRIR MODAL =====
  function abrirModal(modo = 'crear', fraccionData = null) {
    modoModal = modo;
    const modal = document.getElementById('modalFraccion');
    const titulo = document.getElementById('modalFraccionTitulo');
    const codigoField = document.getElementById('fraccionCodigo');
    const idField = document.getElementById('fraccionId');
    const customField = document.getElementById('fraccionCustom');
    const tipoField = document.getElementById('fraccionTipo');
    const notaField = document.getElementById('fraccionNota');
    const btnGuardar = document.getElementById('btnGuardarFraccion');
    
    // Reset form
    document.getElementById('formFraccion').reset();
    idField.value = '';
    document.getElementById('previewNombre').textContent = '—';
    
    if (modo === 'crear') {
        // MODO CREAR
        titulo.textContent = 'Agregar Fracción';
        btnGuardar.textContent = 'Crear Fracción';
        codigoField.disabled = false;
        codigoField.required = true;
        
        // Reset campo custom
        const customLabel = document.getElementById('customLabel');
        const customHint = document.getElementById('customHint');
        customLabel.textContent = '3. Nombre Custom';
        customField.disabled = false;
        customField.required = false;
        customField.style.background = '#fff';
        customField.style.cursor = 'text';
        customHint.textContent = 'Nombre personalizado para esta variación';
        customHint.style.color = '#888';
        
    } else if (modo === 'editar') {
        // MODO EDITAR
        titulo.textContent = 'Editar Fracción';
        btnGuardar.textContent = 'Guardar Cambios';
        fraccionActualId = fraccionData.fraccion_id;
        
        // Deshabilitar código (no se puede cambiar)
        codigoField.disabled = true;
        codigoField.required = false;
        
        // Cargar datos
        idField.value = fraccionData.fraccion_id;
        codigoField.value = fraccionData.codigo;
        tipoField.value = fraccionData.grupo_fracciones || '';
        notaField.value = fraccionData.nota_tecnica || '';
        
        // Determinar si es primera
        const numero = parseInt(fraccionData.fraccion_id.split('-')[2]);
        esPrimera = (numero === 1);
        nombreBase = fraccionData.fraccion_nombre;
        
        // Obtener customs existentes (excluyendo el actual)
        customsExistentes = fraccionesCache
        .filter(f => 
            f.codigo === fraccionData.codigo && 
            f.fraccion_id !== fraccionData.fraccion_id &&
            f.nombre_custom
        )
        .map(f => f.nombre_custom);
        
        // Configurar campo custom
        const customLabel = document.getElementById('customLabel');
        const customHint = document.getElementById('customHint');
        
        if (esPrimera) {
        // FR-XX-001: Custom NO permitido
        customLabel.textContent = '3. Nombre Custom (No permitido para FR-001)';
        customField.value = '';
        customField.disabled = true;
        customField.required = false;
        customField.style.background = '#f5f5f5';
        customField.style.cursor = 'not-allowed';
        customHint.textContent = 'ℹ️ Primera fracción de este código (usa nombre base sin custom)';
        customHint.style.color = '#0d6efd';
        } else {
        // FR-XX-002+: Custom OBLIGATORIO
        customLabel.innerHTML = '3. Nombre Custom * <span style="color:#dc3545;font-weight:600;">⚠️ Requerido</span>';
        customField.value = fraccionData.nombre_custom || '';
        customField.disabled = false;
        customField.required = true;
        customField.style.background = '#fff';
        customField.style.cursor = 'text';
        customHint.textContent = '⚠️ Requerido. Debe ser diferente al nombre base';
        customHint.style.color = '#dc3545';
        }
        
        // Actualizar preview
        actualizarPreview();
    }
    
    modal.classList.add('is-open');
    document.body.style.overflow = 'hidden';
  }

  // ===== CERRAR MODAL =====
  function cerrarModal() {
    const modal = document.getElementById('modalFraccion');
    modal.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  // ===== GUARDAR FRACCIÓN =====
  async function guardarFraccion(event) {
    event.preventDefault();

    const custom = document.getElementById('fraccionCustom').value.trim() || null;
    const tipo = document.getElementById('fraccionTipo').value;
    const nota = document.getElementById('fraccionNota').value.trim() || null;

    // Validación frontend de custom
    if (!esPrimera) {
        if (!custom) {
        alert('⚠️ El nombre custom es obligatorio para fracciones 002+');
        return;
        }
        
        // Validar que no sea igual al nombre base
        if (custom.toUpperCase() === nombreBase.toUpperCase()) {
        alert('❌ El nombre custom no puede ser igual al nombre base');
        return;
        }
        
        // Validar que no esté en customs existentes
        if (customsExistentes.some(c => c.toUpperCase() === custom.toUpperCase())) {
        alert(`❌ Ya existe otra fracción de este código con el custom '${custom}'`);
        return;
        }
    }

    const btnGuardar = document.getElementById('btnGuardarFraccion');
    btnGuardar.disabled = true;

    try {
        let response, data;

        if (modoModal === 'crear') {
        // CREAR
        const codigo = document.getElementById('fraccionCodigo').value;
        btnGuardar.textContent = 'Creando...';

        response = await fetch('/api/fracciones', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
            codigo,
            nombre_custom: custom,
            nota_tecnica: nota,
            grupo_fracciones: tipo
            })
        });

        data = await response.json();

        if (data.success) {
            cerrarModal();
            await cargarFracciones();
            
            // ✅ NUEVO: Preguntar si configurar metodologías
            const configurar = confirm(
            `✅ Fracción ${data.fraccion.fraccion_id} creada correctamente\n\n` +
            `${data.fraccion.nombre_full}\n\n` +
            `¿Deseas configurar las metodologías ahora?`
            );
            
            if (configurar) {
            window.location.href = `/catalogos/fracciones/${data.fraccion.fraccion_id}/metodologias`;
            }
        } else {
            alert('❌ Error: ' + data.error);
        }

        } else if (modoModal === 'editar') {
        // EDITAR
        btnGuardar.textContent = 'Guardando...';

        response = await fetch(`/api/fracciones/${fraccionActualId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
            nombre_custom: custom,
            nota_tecnica: nota,
            grupo_fracciones: tipo
            })
        });

        data = await response.json();

        if (data.success) {
            alert(`✅ Fracción ${data.fraccion.fraccion_id} actualizada correctamente\n\n${data.fraccion.nombre_full}`);
            cerrarModal();
            await cargarFracciones();
        } else {
            alert('❌ Error: ' + data.error);
        }
        }

    } catch (error) {
        console.error('❌ Error:', error);
        alert('❌ Error de conexión');
    } finally {
        btnGuardar.disabled = false;
        btnGuardar.textContent = modoModal === 'crear' ? 'Crear Fracción' : 'Guardar Cambios';
    }
  }

  // ===== EVENT LISTENERS =====
  // ===== ELIMINAR FRACCIÓN =====
  async function eliminarFraccion(fraccionId, nombreFull) {
    const confirmar = confirm(
      `¿Estás seguro de eliminar la fracción ${fraccionId}?\n\n` +
      `${nombreFull}\n\n` +
      `Esta acción no se puede deshacer.`
    );

    if (!confirmar) return;

    try {
      const response = await fetch(`/api/fracciones/${fraccionId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        alert(`✅ Fracción ${fraccionId} eliminada correctamente`);
        await cargarFracciones();
      } else {
        // Mostrar error detallado
        let mensaje = `❌ No se puede eliminar\n\n${data.error}`;
        
        if (data.detalles) {
          mensaje += '\n\nEn uso en:';
          if (data.detalles.metodologias > 0) mensaje += `\n• ${data.detalles.metodologias} metodología(s)`;
          if (data.detalles.sops > 0) mensaje += `\n• ${data.detalles.sops} SOP(s)`;
          if (data.detalles.elemento_sets > 0) mensaje += `\n• ${data.detalles.elemento_sets} elemento set(s)`;
          if (data.detalles.kits > 0) mensaje += `\n• ${data.detalles.kits} kit(s)`;
        }
        
        alert(mensaje);
      }

    } catch (error) {
      console.error('❌ Error:', error);
      alert('❌ Error de conexión');
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

  // Event listeners de botones editar/eliminar
  document.addEventListener('click', function(e) {
    if (e.target.closest('.btn-editar-fraccion')) {
      const btn = e.target.closest('.btn-editar-fraccion');
      const fraccionId = btn.dataset.id;
      
      const fraccionData = fraccionesCache.find(f => f.fraccion_id === fraccionId);
      
      if (fraccionData) {
        abrirModal('editar', fraccionData);
      }
    }

    if (e.target.closest('.btn-eliminar-fraccion')) {
      const btn = e.target.closest('.btn-eliminar-fraccion');
      const fraccionId = btn.dataset.id;
      
      // Buscar datos de la fracción para mostrar nombre completo
      const fraccionData = fraccionesCache.find(f => f.fraccion_id === fraccionId);
      
      if (fraccionData) {
        // Calcular nombre_full
        let nombreFull = fraccionData.fraccion_nombre;
        if (fraccionData.nombre_custom) {
          nombreFull = `${fraccionData.fraccion_nombre} — ${fraccionData.nombre_custom}`;
        }
        
        eliminarFraccion(fraccionId, nombreFull);
      }
    }

    // Event listeners de botones (busca esta sección y agrega el if de metodologías)
    document.addEventListener('click', function(e) {
        // ✅ NUEVO: Botón metodologías
        if (e.target.closest('.btn-metodologias')) {
        const btn = e.target.closest('.btn-metodologias');
        const fraccionId = btn.dataset.id;
        
        // Redirigir a página de metodologías
        window.location.href = `/catalogos/fracciones/${fraccionId}/metodologias`;
        return;
        }
        
        if (e.target.closest('.btn-editar-fraccion')) {
        // ... código existente ...
        }

        if (e.target.closest('.btn-eliminar-fraccion')) {
        // ... código existente ...
      }
    });
  });

  // ✅ Inicializar
  init();

})();