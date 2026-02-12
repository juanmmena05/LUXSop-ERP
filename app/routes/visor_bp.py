# visor_bp.py - Blueprint para visor de documentos PDF
from flask import Blueprint, render_template, abort, request, redirect, url_for, Response
from flask_login import login_required
from ..extensions import db
from ..models import InstructivoTrabajo, TMO, HerramientaUso, FichaReceta, Fraccion

visor_bp = Blueprint("visor", __name__)


@visor_bp.route("/visor/instructivo/<int:instructivo_id>")
@login_required
def visor_instructivo(instructivo_id):
    """Muestra Instructivo de Trabajo (Nivel 2)"""
    instructivo = InstructivoTrabajo.query.get_or_404(instructivo_id)
    fraccion = instructivo.fraccion
    
    # Obtener parámetros de la URL
    fecha = request.args.get('fecha')
    personal_id = request.args.get('personal_id')
    tarea_id = request.args.get('tarea_id')  # ← AGREGAR ESTA LÍNEA
    
    # Detectar si es móvil
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = any(x in user_agent for x in ['iphone', 'ipad', 'android', 'mobile'])
    
    return render_template(
        "visor/visor_instructivo.html",
        instructivo=instructivo,
        fraccion=fraccion,
        fecha=fecha,
        personal_id=personal_id,
        tarea_id=tarea_id,  # ← AGREGAR ESTA LÍNEA
        is_mobile=is_mobile
    )


@visor_bp.route("/doc/<codigo>")
@login_required
def resolver_documento(codigo):
    """Traduce código (TM-BA-001) → documento real y redirige al visor"""
    
    # Capturar parámetros de navegación
    origen_codigo = request.args.get('from', '')
    fecha = request.args.get('fecha')
    personal_id = request.args.get('personal_id')
    
    # Buscar en TMO
    doc = TMO.query.filter_by(codigo=codigo).first()
    if doc:
        return redirect(url_for('visor.visor_documento', 
                                documento_id=doc.tmo_id, 
                                tipo='tmo',
                                origen_codigo=origen_codigo,
                                fecha=fecha,
                                personal_id=personal_id))
    
    # Buscar en HerramientaUso
    doc = HerramientaUso.query.filter_by(codigo=codigo).first()
    if doc:
        return redirect(url_for('visor.visor_documento',
                                documento_id=doc.herramienta_uso_id,
                                tipo='herramienta',
                                origen_codigo=origen_codigo,
                                fecha=fecha,
                                personal_id=personal_id))
    
    # Buscar en FichaReceta
    doc = FichaReceta.query.filter_by(codigo=codigo).first()
    if doc:
        return redirect(url_for('visor.visor_documento',
                                documento_id=doc.ficha_receta_id,
                                tipo='ficha',
                                origen_codigo=origen_codigo,
                                fecha=fecha,
                                personal_id=personal_id))
    
    abort(404, f"Documento no encontrado: {codigo}")


@visor_bp.route("/visor/documento/<int:documento_id>")
@login_required
def visor_documento(documento_id):
    """Muestra TMO/Herramienta/Ficha (Nivel 3)"""
    tipo = request.args.get('tipo')
    origen_codigo = request.args.get('origen_codigo', '')
    fecha = request.args.get('fecha')
    personal_id = request.args.get('personal_id')
    
    # Detectar si es móvil
    user_agent = request.headers.get('User-Agent', '').lower()
    is_mobile = any(x in user_agent for x in ['iphone', 'ipad', 'android', 'mobile'])
    
    documento = None
    if tipo == 'tmo':
        documento = TMO.query.get_or_404(documento_id)
    elif tipo == 'herramienta':
        documento = HerramientaUso.query.get_or_404(documento_id)
    elif tipo == 'ficha':
        documento = FichaReceta.query.get_or_404(documento_id)
    else:
        abort(400, "Tipo de documento inválido")
    
    return render_template(
        "visor/visor_documento.html",
        documento=documento,
        tipo=tipo,
        origen_codigo=origen_codigo,
        fecha=fecha,
        personal_id=personal_id,
        is_mobile=is_mobile
    )


@visor_bp.route("/pdf-proxy")
@login_required
def pdf_proxy():
    """Proxy para servir PDFs de Azure con headers correctos"""
    import requests
    
    pdf_url = request.args.get('url')
    if not pdf_url:
        abort(400, "URL del PDF requerida")
    
    # Validar que sea de Azure
    if 'sopstorageprod.blob.core.windows.net' not in pdf_url:
        abort(403, "URL no autorizada")
    
    try:
        # Descargar PDF de Azure
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()
        
        # Servir con headers correctos
        return Response(
            response.content,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': 'inline; filename="documento.pdf"',
                'Content-Type': 'application/pdf'
            }
        )
    except Exception as e:
        abort(500, f"Error al cargar PDF: {str(e)}")