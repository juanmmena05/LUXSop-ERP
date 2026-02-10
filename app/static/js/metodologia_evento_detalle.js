// ===== METODOLOGÍA EVENTO - CRUD DE PASOS =====
(function() {
  'use strict';

  // Variables globales
  let metodologiaData = window.METODOLOGIA_DATA || {};
  let pasosActuales = [];
  let sortableInstance = null;

  // ===== INICIALIZAR =====
  async function init() {
    await cargarMetodologia();
    inicializarBotones();
  }

  // ===== CARGAR METODOLOGÍA =====
  async function cargarMetodologia() {
    try {
      const response = await fetch(`/api/metodologias-eventos/${metodologiaData.metodologia_fraccion_id}`);
      const data = await response.json();
      
      if (data.success) {
        pasosActuales = data.metodologia.pasos.map(p => ({
          numero_paso: p.numero_paso,
          descripcion: p.descripcion
        }));
        
        console.log('✅ Metodología cargada:', data.metodologia);
        renderPasos();
      } else {
        mostrarError('Error al cargar metodología: ' + data.error);
      }
    } catch (error) {
      console.error('❌ Error al cargar metodología:', error);
      mostrarError('Error de conexión');
    }
  }

  // ===== RENDERIZAR PASOS =====
  function renderPasos() {
    const pasosContainer = document.getElementById('pasosContainer');
    
    if (pasosActuales.length === 0) {
      pasosContainer.innerHTML = `
        <div class="empty-state">
          <div style="font-size:3rem;margin-bottom:12px;">📋</div>
          <div style="font-size:1.1rem;margin-bottom:8px;">No hay pasos configurados</div>
          <div style="font-size:.9rem;color:#999;">Agrega el primer paso para esta metodología</div>
        </div>
        <button class="btn-add-paso" onclick="window.agregarPaso()">
          + Agregar Paso
        </button>
      `;
      return;
    }
    
    let html = '<div id="pasosList">';
    
    pasosActuales.forEach((paso, index) => {
      html += `
        <div class="paso-item" data-index="${index}">
          <div class="drag-handle">☰</div>
          <div class="paso-numero">${index + 1}.</div>
          <input 
            type="text" 
            class="paso-input" 
            value="${paso.descripcion}"
            data-index="${index}"
            placeholder="Descripción del paso..."
          >
          <button class="btn-delete-paso" onclick="window.eliminarPaso(${index})">
            🗑️
          </button>
        </div>
      `;
    });
    
    html += '</div>';
    html += `
      <button class="btn-add-paso" onclick="window.agregarPaso()">
        + Agregar Paso
      </button>
    `;
    
    pasosContainer.innerHTML = html;
    
    // Inicializar Sortable (drag & drop)
    inicializarDragDrop();
    
    // Event listeners para inputs
    document.querySelectorAll('.paso-input').forEach(input => {
      input.addEventListener('input', function() {
        const index = parseInt(this.dataset.index);
        pasosActuales[index].descripcion = this.value;
      });
    });
  }

  // ===== INICIALIZAR DRAG & DROP =====
  function inicializarDragDrop() {
    const pasosList = document.getElementById('pasosList');
    
    if (!pasosList) return;
    
    if (sortableInstance) {
      sortableInstance.destroy();
    }
    
    sortableInstance = Sortable.create(pasosList, {
      handle: '.drag-handle',
      animation: 150,
      ghostClass: 'dragging',
      onEnd: function(evt) {
        // Reordenar array
        const movedItem = pasosActuales.splice(evt.oldIndex, 1)[0];
        pasosActuales.splice(evt.newIndex, 0, movedItem);
        
        // Re-renderizar
        renderPasos();
        
        mostrarStatus('Orden actualizado');
      }
    });
  }

  // ===== AGREGAR PASO =====
  window.agregarPaso = function() {
    const nuevoNumero = pasosActuales.length + 1;
    
    pasosActuales.push({
      numero_paso: nuevoNumero,
      descripcion: ''
    });
    
    renderPasos();
    
    // Focus en el nuevo input
    setTimeout(() => {
      const inputs = document.querySelectorAll('.paso-input');
      const lastInput = inputs[inputs.length - 1];
      if (lastInput) lastInput.focus();
    }, 100);
    
    mostrarStatus('Paso agregado');
  };

  // ===== ELIMINAR PASO =====
  window.eliminarPaso = function(index) {
    const confirmar = confirm('¿Eliminar este paso?');
    
    if (!confirmar) return;
    
    pasosActuales.splice(index, 1);
    renderPasos();
    
    mostrarStatus('Paso eliminado');
  };

  // ===== GUARDAR METODOLOGÍA =====
  async function guardarMetodologia() {
    // Validar que haya al menos 1 paso
    if (pasosActuales.length === 0) {
      alert('⚠️ Debes agregar al menos 1 paso');
      return;
    }
    
    // Validar que todos los pasos tengan descripción
    const pasosVacios = pasosActuales.filter(p => !p.descripcion.trim());
    if (pasosVacios.length > 0) {
      alert('⚠️ Todos los pasos deben tener una descripción');
      return;
    }
    
    const btnGuardar = document.getElementById('btnGuardarMetodologia');
    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';
    
    try {
      // Renumerar pasos (por si hubo reordenamientos)
      const pasosLimpios = pasosActuales.map((p, index) => ({
        numero_paso: index + 1,
        descripcion: p.descripcion.trim()
      }));
      
      const response = await fetch(
        `/api/metodologias-eventos/${metodologiaData.metodologia_fraccion_id}/pasos`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pasos: pasosLimpios })
        }
      );
      
      const data = await response.json();
      
      if (data.success) {
        alert(`✅ Metodología guardada correctamente\n\n${data.message}`);
        
        // Recargar datos
        await cargarMetodologia();
        
        mostrarStatus('Guardado exitoso', 'success');
      } else {
        alert('❌ Error: ' + data.error);
      }
      
    } catch (error) {
      console.error('❌ Error:', error);
      alert('❌ Error de conexión');
    } finally {
      btnGuardar.disabled = false;
      btnGuardar.textContent = 'Guardar Metodología';
    }
  }

  // ===== INICIALIZAR BOTONES =====
  function inicializarBotones() {
    document.getElementById('btnGuardarMetodologia')?.addEventListener('click', guardarMetodologia);
  }

  // ===== MOSTRAR STATUS =====
  function mostrarStatus(mensaje, tipo = 'info') {
    const statusEl = document.getElementById('statusMessage');
    statusEl.textContent = mensaje;
    statusEl.style.color = tipo === 'success' ? '#198754' : '#888';
    
    setTimeout(() => {
      statusEl.textContent = '';
    }, 3000);
  }

  // ===== MOSTRAR ERROR =====
  function mostrarError(mensaje) {
    const pasosContainer = document.getElementById('pasosContainer');
    pasosContainer.innerHTML = `
      <div class="empty-state">
        <div style="font-size:3rem;margin-bottom:12px;">❌</div>
        <div style="font-size:1.1rem;margin-bottom:8px;">${mensaje}</div>
      </div>
    `;
  }

  // ✅ Inicializar al cargar
  init();

})();