"""Deterministic Gutenberg compilation of validated design sections."""
from html import escape
import re
from muse.commerce.design_models import StoreDesignDocument


def render_design(document: StoreDesignDocument, media_urls: dict[str,str] | None = None) -> str:
    from muse.commerce.theme import block,product_collection
    media_urls = media_urls or {}
    output=[]
    for section in document.home_sections:
        if not section.enabled: continue
        props=section.props
        body=block('heading',{'level':1 if section.kind=='hero' else 2},'<h'+('1' if section.kind=='hero' else '2')+' class="wp-block-heading">'+escape(props.title)+'</h'+('1' if section.kind=='hero' else '2')+'>')
        if props.media_id:
            url=media_urls.get(props.media_id)
            if not url or not re.fullmatch(r'/wp-content/uploads/[a-zA-Z0-9_./-]+',url) or '..' in url:
                raise ValueError('Design image needs verified WordPress media mapping')
            body+=block('image',inner='<figure class="wp-block-image"><img src="'+escape(url,quote=True)+'" alt="'+escape(props.alt,quote=True)+'"/></figure>')
        if props.text: body+=block('paragraph',inner='<p>'+escape(props.text).replace('\n','<br>')+'</p>')
        for item in props.items:
            body+=block('paragraph',inner='<p>'+escape(item)+'</p>')
        if section.kind=='products': body+=product_collection(inherit=False)
        if props.button_label:
            body+=block('paragraph',inner='<p><a class="crew-design-button" href="'+props.link+'">'+escape(props.button_label)+'</a></p>')
        output.append(block('group',{'className':'crew-design-section crew-design-'+section.kind},'<div class="wp-block-group crew-design-section crew-design-'+section.kind+'">'+body+'</div>'))
    return ''.join(output)
