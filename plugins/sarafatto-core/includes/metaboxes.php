<?php
/** Structured admin controls for Products. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_add_product_meta_boxes() {
	remove_meta_box( 'postcustom', 'sarafatto_prodotto', 'normal' );
	remove_meta_box( 'postexcerpt', 'sarafatto_prodotto', 'normal' );
	add_meta_box( 'sarafatto-product-content', __( 'Scheda prodotto', 'sarafatto-core' ), 'sarafatto_render_product_content_meta_box', 'sarafatto_prodotto', 'normal', 'high' );
	add_meta_box( 'sarafatto-product-gallery', __( 'Gallery facoltativa', 'sarafatto-core' ), 'sarafatto_render_product_gallery_meta_box', 'sarafatto_prodotto', 'normal', 'default' );
}
add_action( 'add_meta_boxes_sarafatto_prodotto', 'sarafatto_add_product_meta_boxes' );

function sarafatto_render_product_content_meta_box( $post ) {
	wp_nonce_field( 'sarafatto_save_product_meta_' . $post->ID, 'sarafatto_product_content_nonce' );
	$label = get_post_meta( $post->ID, 'sarafatto_editorial_label', true );
	$story = get_post_meta( $post->ID, 'sarafatto_story', true );
	$flags = sarafatto_get_product_flags( $post->ID );
	?>
	<p><label for="sarafatto-editorial-label"><strong><?php esc_html_e( 'Etichetta editoriale', 'sarafatto-core' ); ?></strong></label><input class="widefat" type="text" id="sarafatto-editorial-label" name="sarafatto_editorial_label" value="<?php echo esc_attr( is_scalar( $label ) ? $label : '' ); ?>"></p>
	<p><label for="excerpt"><strong><?php esc_html_e( 'Breve descrizione', 'sarafatto-core' ); ?></strong></label><textarea class="widefat" id="excerpt" name="excerpt" rows="4"><?php echo esc_textarea( $post->post_excerpt ); ?></textarea><span class="description"><?php esc_html_e( 'Usata nelle card e nelle anteprime.', 'sarafatto-core' ); ?></span></p>
	<div class="sarafatto-story-field"><label for="sarafatto_story"><strong><?php esc_html_e( 'Racconto', 'sarafatto-core' ); ?></strong></label><?php wp_editor( is_string( $story ) ? $story : '', 'sarafatto_story', array( 'textarea_name' => 'sarafatto_story', 'textarea_rows' => 8, 'media_buttons' => false, 'teeny' => true, 'quicktags' => array( 'buttons' => 'strong,em,link,ul,ol,li,close' ), 'tinymce' => array( 'toolbar1' => 'bold,italic,link,unlink,bullist,numlist,undo,redo', 'toolbar2' => '', 'block_formats' => 'Paragrafo=p', 'menubar' => false, 'height' => 240 ) ) ); ?></div>
	<fieldset><legend><strong><?php esc_html_e( 'Visibilità editoriale', 'sarafatto-core' ); ?></strong></legend>
		<p><label><input type="checkbox" name="sarafatto_is_new" value="1" <?php checked( $flags['is_new'] ); ?>> <?php esc_html_e( 'Mostra tra le Novità', 'sarafatto-core' ); ?></label></p>
		<p><label><input type="checkbox" name="sarafatto_is_featured" value="1" <?php checked( $flags['is_featured'] ); ?>> <?php esc_html_e( 'Mostra in evidenza', 'sarafatto-core' ); ?></label></p>
	</fieldset>
	<?php
}

function sarafatto_render_product_gallery_meta_box( $post ) {
	$ids = sarafatto_sanitize_gallery_ids( get_post_meta( $post->ID, 'sarafatto_gallery', true ) );
	wp_nonce_field( 'sarafatto_save_product_gallery_' . $post->ID, 'sarafatto_product_gallery_nonce' );
	?>
	<div class="sarafatto-gallery-control"><input type="hidden" id="sarafatto-gallery-ids" name="sarafatto_gallery" value="<?php echo esc_attr( implode( ',', $ids ) ); ?>"><ul id="sarafatto-gallery-preview" class="sarafatto-gallery-preview">
	<?php foreach ( $ids as $id ) : if ( ! wp_attachment_is_image( $id ) ) { continue; } $title = get_the_title( $id ); ?>
	<li class="sarafatto-gallery-preview__item" data-attachment-id="<?php echo esc_attr( $id ); ?>"><?php echo wp_get_attachment_image( $id, 'thumbnail', false, array( 'alt' => '' ) ); ?><button type="button" class="button-link-delete sarafatto-gallery-preview__remove" aria-label="<?php echo esc_attr( sprintf( __( 'Rimuovi %s dalla gallery', 'sarafatto-core' ), $title ? $title : __( 'immagine', 'sarafatto-core' ) ) ); ?>"><?php esc_html_e( 'Rimuovi', 'sarafatto-core' ); ?></button></li>
	<?php endforeach; ?></ul><button type="button" class="button" id="sarafatto-gallery-add"><?php esc_html_e( 'Aggiungi immagini', 'sarafatto-core' ); ?></button><p id="sarafatto-gallery-status" class="screen-reader-text" role="status" aria-live="polite"></p><p class="description"><?php esc_html_e( 'Seleziona immagini dalla libreria Media. Per rimuoverle usa il pulsante sulla miniatura.', 'sarafatto-core' ); ?></p></div>
	<?php
}

function sarafatto_enqueue_product_admin_assets( $hook_suffix ) {
	if ( ! in_array( $hook_suffix, array( 'post.php', 'post-new.php' ), true ) ) { return; }
	$screen = get_current_screen();
	if ( ! $screen || 'sarafatto_prodotto' !== $screen->post_type ) { return; }
	wp_enqueue_media();
	wp_enqueue_style( 'sarafatto-product-admin', SARAFATTO_CORE_URL . 'assets/css/product-admin.css', array(), SARAFATTO_CORE_VERSION );
	wp_enqueue_script( 'sarafatto-product-gallery', SARAFATTO_CORE_URL . 'assets/js/product-gallery.js', array( 'jquery', 'media-editor', 'media-views' ), SARAFATTO_CORE_VERSION, true );
	wp_localize_script( 'sarafatto-product-gallery', 'sarafattoProductGalleryL10n', array( 'title' => __( 'Seleziona le immagini della gallery', 'sarafatto-core' ), 'button' => __( 'Aggiungi alla gallery', 'sarafatto-core' ), 'remove' => __( 'Rimuovi', 'sarafatto-core' ), 'removeLabel' => __( 'Rimuovi %s dalla gallery', 'sarafatto-core' ), 'updated' => __( 'Gallery aggiornata.', 'sarafatto-core' ), 'removed' => __( 'Immagine rimossa dalla gallery.', 'sarafatto-core' ) ) );
}
add_action( 'admin_enqueue_scripts', 'sarafatto_enqueue_product_admin_assets' );

function sarafatto_save_product_meta( $post_id, $post ) {
	$content_nonce = isset( $_POST['sarafatto_product_content_nonce'] ) && is_scalar( $_POST['sarafatto_product_content_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['sarafatto_product_content_nonce'] ) ) : '';
	$gallery_nonce = isset( $_POST['sarafatto_product_gallery_nonce'] ) && is_scalar( $_POST['sarafatto_product_gallery_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['sarafatto_product_gallery_nonce'] ) ) : '';
	$content_ok = $content_nonce && wp_verify_nonce( $content_nonce, 'sarafatto_save_product_meta_' . $post_id );
	$gallery_ok = $gallery_nonce && wp_verify_nonce( $gallery_nonce, 'sarafatto_save_product_gallery_' . $post_id );
	if ( ! $content_ok && ! $gallery_ok ) { return; }
	if ( ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) || wp_is_post_revision( $post_id ) || ! $post instanceof WP_Post || 'sarafatto_prodotto' !== $post->post_type || ! current_user_can( 'edit_post', $post_id ) ) { return; }
	if ( $content_ok ) {
		$label = isset( $_POST['sarafatto_editorial_label'] ) && is_scalar( $_POST['sarafatto_editorial_label'] ) ? sanitize_text_field( wp_unslash( $_POST['sarafatto_editorial_label'] ) ) : '';
		$story = isset( $_POST['sarafatto_story'] ) && is_scalar( $_POST['sarafatto_story'] ) ? sarafatto_sanitize_story( wp_unslash( $_POST['sarafatto_story'] ) ) : '';
		$is_new = isset( $_POST['sarafatto_is_new'] ) && is_scalar( $_POST['sarafatto_is_new'] ) && '1' === sanitize_text_field( wp_unslash( $_POST['sarafatto_is_new'] ) );
		$is_featured = isset( $_POST['sarafatto_is_featured'] ) && is_scalar( $_POST['sarafatto_is_featured'] ) && '1' === sanitize_text_field( wp_unslash( $_POST['sarafatto_is_featured'] ) );
		sarafatto_update_or_delete_meta( $post_id, 'sarafatto_editorial_label', $label );
		sarafatto_update_or_delete_meta( $post_id, 'sarafatto_story', '' !== trim( wp_strip_all_tags( $story ) ) ? $story : '' );
		sarafatto_update_or_delete_meta( $post_id, 'sarafatto_is_new', $is_new ? '1' : '' );
		sarafatto_update_or_delete_meta( $post_id, 'sarafatto_is_featured', $is_featured ? '1' : '' );
	}
	if ( $gallery_ok ) {
		$raw = isset( $_POST['sarafatto_gallery'] ) && is_scalar( $_POST['sarafatto_gallery'] ) ? sanitize_text_field( wp_unslash( $_POST['sarafatto_gallery'] ) ) : '';
		$ids = '' !== $raw ? sarafatto_sanitize_gallery_ids( explode( ',', $raw ) ) : array();
		sarafatto_update_or_delete_meta( $post_id, 'sarafatto_gallery', $ids );
	}
}
add_action( 'save_post_sarafatto_prodotto', 'sarafatto_save_product_meta', 10, 2 );

function sarafatto_update_or_delete_meta( $post_id, $meta_key, $value ) {
	if ( '' === $value || array() === $value ) { delete_post_meta( $post_id, $meta_key ); return; }
	update_post_meta( $post_id, $meta_key, $value );
}

