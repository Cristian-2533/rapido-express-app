// Variable para guardar el ID del pedido que se está editando
let pedidoSeleccionadoId = null;
let fotoEvidenciaBase64 = null;

/**
 * Abre el modal y llena los datos del pedido seleccionado.
 */
function verDetalle(pedidoId) {
  pedidoSeleccionadoId = pedidoId;
  fotoEvidenciaBase64 = null;

  // Limpiar vista previa de la foto
  const imgPreview = document.getElementById('imgPreviewEvidencia');
  if (imgPreview) {
    imgPreview.src = '';
    imgPreview.classList.add('hidden');
  }

  const labelFoto = document.getElementById('fotoLabelText');
  if (labelFoto) {
    labelFoto.innerText = "Tomar foto del comprobante";
  }

  // Traer los datos del pedido desde el servidor
  fetch(`/api/pedidos/${pedidoId}`, {
    headers: { 
      'Authorization': `Bearer ${localStorage.getItem('token') || ''}` 
    }
  })
  .then(res => {
    if (!res.ok) throw new Error("No se pudo cargar el pedido.");
    return res.json();
  })
  .then(pedido => {
    // Colocar la información en los textos del modal
    document.getElementById('detCodigoPedido').innerText = pedido.codigo_pedido || `PED-${pedido.id}`;
    document.getElementById('detNombreCliente').innerText = pedido.nombre_cliente;
    document.getElementById('detDireccion').innerText = pedido.direccion;
    document.getElementById('detBarrioCiudad').innerText = `${pedido.barrio || ''} — ${pedido.ciudad || 'Medellín'}`;
    
    const detTel = document.getElementById('detTelefono');
    detTel.innerText = pedido.telefono || 'Sin teléfono';
    detTel.href = pedido.telefono ? `tel:${pedido.telefono}` : '#';

    document.getElementById('detDescripcion').innerText = pedido.descripcion || 'Sin detalle';
    document.getElementById('detNotas').innerText = pedido.notas_entrega || 'Sin notas';
    document.getElementById('detMetodoPago').innerText = `Método de pago: ${pedido.metodo_pago || 'Efectivo'}`;
    
    const monto = Number(pedido.monto_total || 0).toLocaleString('es-CO');
    document.getElementById('detMontoTotal').innerText = `$ ${monto}`;

    // Marcar la opción del estado actual
    const radioEstado = document.querySelector(`input[name="nuevoEstado"][value="${pedido.estado}"]`);
    if (radioEstado) {
      radioEstado.checked = true;
    }

    // Cargar la observación si ya tenía una
    const inputObs = document.getElementById('inputObservacion');
    if (inputObs) {
      inputObs.value = pedido.observacion || '';
    }

    // Mostrar el modal
    document.getElementById('modalDetallePedido').classList.remove('hidden');
  })
  .catch(err => {
    alert(err.message || "Error al conectar con el servidor");
  });
}

/**
 * Cierra la ventana del detalle.
 */
function cerrarModalDetalle() {
  document.getElementById('modalDetallePedido').classList.add('hidden');
}

/**
 * Muestra la vista previa de la foto tomada o seleccionada.
 */
function previewFoto(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = function(e) {
    fotoEvidenciaBase64 = e.target.result;

    const imgPreview = document.getElementById('imgPreviewEvidencia');
    if (imgPreview) {
      imgPreview.src = fotoEvidenciaBase64;
      imgPreview.classList.remove('hidden');
    }

    const labelFoto = document.getElementById('fotoLabelText');
    if (labelFoto) {
      labelFoto.innerText = "Cambiar foto de comprobante";
    }
  };

  reader.readAsDataURL(file);
}

/**
 * Envía la actualización al servidor cuando le das al botón "Guardar estado".
 */
function guardarEstadoPedido(event) {
  event.preventDefault();

  if (!pedidoSeleccionadoId) {
    alert("No hay un pedido seleccionado.");
    return;
  }

  const radioSeleccionado = document.querySelector('input[name="nuevoEstado"]:checked');
  if (!radioSeleccionado) {
    alert("Selecciona un estado.");
    return;
  }

  const payload = {
    estado: radioSeleccionado.value,
    observacion: document.getElementById('inputObservacion')?.value || '',
    evidencia_foto: fotoEvidenciaBase64
  };

  const btnSubmit = document.getElementById('btnGuardarEstado');
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.innerText = "Guardando...";
  }

  fetch(`/api/pedidos/${pedidoSeleccionadoId}/estado`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
    },
    body: JSON.stringify(payload)
  })
  .then(res => {
    if (!res.ok) throw new Error("No se pudo guardar la actualización.");
    return res.json();
  })
  .then(data => {
    alert("¡Estado guardado correctamente!");
    cerrarModalDetalle();

    // Recargar la lista si existe la función
    if (typeof cargarPedidosRepartidor === 'function') {
      cargarPedidosRepartidor();
    }
  })
  .catch(err => {
    alert(err.message || "Error al guardar");
  })
  .finally(() => {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.innerText = "Guardar estado";
    }
  });
}