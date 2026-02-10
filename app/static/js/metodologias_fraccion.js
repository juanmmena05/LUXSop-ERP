// ===== METODOLOGÍAS FRACCIÓN - CRUD COMPLETO =====
(function() {
  'use strict';

  // Variables globales
  let fraccionData = window.FRACCION_DATA || {};
  let metodologiasData = {};
  let nivelActual = 1;  // Básica por defecto
  let pasosActuales = [];
  let sortableInstance = null;
  
  const nivel_map = {
    1: 'B',
    2: 'M', 
    3: 'P',
    4: 'E'
  };

  // ===== INICIALIZAR =====
  async function init() {
    await cargarMetodologias();
    inicializarTabs();
    inicializarBotones();
    mostrarNivel(1);
  }

  // ===== CARGAR METODOLOGÍAS =====
  async function cargarMetodologias() {
    try {
      const response = await fetch(`/api/fracciones/${fraccionData.fraccion_id}/metodologias`);
      const data = await response.json();
      
      if (data.success) {
        metodologiasData = data.metodologias;
        console.log('✅ Metodologías cargadas:', metodologiasData);
      } else {
        mostrarError('Error al cargar metodologías: ' + data.error);
      }
    } catch (error) {
      console.error('❌ Error al cargar metodologías:', error);
      mostrarError('Error de conexión');
    }
  }

  // ===== INICIALIZAR TABS =====
  function inicializarTabs() {
    const tabs = document.querySelectorAll('.tab');
    
    tabs.forEach(tab => {
      tab.addEventListener('click', function() {
        const nivel = parseInt(this.dataset.nivel);
        
        // Cambiar tab activo
        tabs.forEach(t => t.classList.remove('active'));
        this.classList.add('active');
        
        // Mostrar metodología de ese nivel
        mostrarNivel(nivel);
      });
    });
  }

  // ===== MOSTRAR NIVEL =====
  function mostrarNivel(nivel) {
    nivelActual = nivel;
    
    const metodologia = metodologiasData[nivel.toString()];
    const metodologiaIdEl = document.getElementById('metodologiaId');
    const pasosContainer = document.getElementById('pasosContainer');
    
    if (metodologia) {
      // Existe metodología
      metodologiaIdEl.textContent = metodologia.metodologia_base_id;
      pasosActuales = [...metodologia.pasos];  // Copia
      renderPasos();
    } else {
      // No existe metodología para este nivel
      const letra = nivel_map[nivel];
      const metodologiaId = `MB-${fraccionData.codigo}-${fraccionData.fraccion_id.split('-')[2]}-${letra}`;
      
      metodologiaIdEl.textContent = `${metodologiaId} (nueva)`;
      pasosActuales = [];
      renderPasos();
    }
  }

  // ===== RENDERIZAR PASOS =====
  function renderPasos() {
    const pasosContainer = document.getElementById('pasosContainer');
    
    if (pasosActuales.length === 0) {
      pasosContainer.innerHTML = `
        <div class="empty-state">
          <div style="font-size:3rem;margin-bottom:12px;">📝</div>
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
            value="${paso.instruccion}"
            data-index="${index}"
            placeholder="Instrucción del paso..."
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
        pasosActuales[index].instruccion = this.value;
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
    const nuevoOrden = pasosActuales.length + 1;
    
    pasosActuales.push({
      orden: nuevoOrden,
      instruccion: ''
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
    
    // Validar que todos los pasos tengan instrucción
    const pasosVacios = pasosActuales.filter(p => !p.instruccion.trim());
    if (pasosVacios.length > 0) {
      alert('⚠️ Todos los pasos deben tener una instrucción');
      return;
    }
    
    const btnGuardar = document.getElementById('btnGuardarMetodologia');
    btnGuardar.disabled = true;
    btnGuardar.textContent = 'Guardando...';
    
    try {
      // Renumerar pasos (por si hubo reordenamientos)
      const pasosLimpios = pasosActuales.map((p, index) => ({
        orden: index + 1,
        instruccion: p.instruccion.trim()
      }));
      
      const response = await fetch(
        `/api/fracciones/${fraccionData.fraccion_id}/metodologias/${nivelActual}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pasos: pasosLimpios })
        }
      );
      
      const data = await response.json();
      
      if (data.success) {
        alert(`✅ Metodología guardada correctamente\n\n${data.metodologia_base_id}`);
        
        // Recargar datos
        await cargarMetodologias();
        mostrarNivel(nivelActual);
        
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