<?php
/** Occasion and gift-idea term metadata, admin controls, and shared icon registry. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Controlled icon vocabulary shared by Occasioni and Idee regalo. */
function sarafatto_get_editorial_icons() {
	return array(
		'sparkles' => __( 'Scintille', 'sarafatto-core' ),
		'gift'     => __( 'Regalo', 'sarafatto-core' ),
		'heart'    => __( 'Cuore', 'sarafatto-core' ),
		'sun'      => __( 'Sole', 'sarafatto-core' ),
		'flower'   => __( 'Fiore', 'sarafatto-core' ),
		'star'     => __( 'Stella', 'sarafatto-core' ),
		'home'     => __( 'Casa', 'sarafatto-core' ),
		'bag'      => __( 'Borsa', 'sarafatto-core' ),
		'party'    => __( 'Festa', 'sarafatto-core' ),
		'leaf'     => __( 'Foglia', 'sarafatto-core' ),
	);
}

/** Render a whitelisted symbol from the shared static SVG sprite. */
function sarafatto_get_term_icon_markup( $icon, $class_name = '' ) {
	$icons = sarafatto_get_editorial_icons();
	$icon  = is_scalar( $icon ) ? sanitize_key( (string) $icon ) : '';
	if ( ! isset( $icons[ $icon ] ) ) {
		return '';
	}

	$classes    = array( 'sarafatto-editorial-icon' );
	$class_name = is_scalar( $class_name ) ? sanitize_html_class( (string) $class_name ) : '';
	if ( $class_name ) {
		$classes[] = $class_name;
	}
	$symbol_url = SARAFATTO_CORE_URL . 'assets/icons/editorial-icons.svg#' . rawurlencode( $icon );

	return sprintf(
		'<svg class="%1$s" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="%2$s"></use></svg>',
		esc_attr( implode( ' ', $classes ) ),
		esc_url( $symbol_url )
	);
}

function sarafatto_register_term_meta() {
	$term_meta = array(
		'sarafatto_occasione' => array(
			'sarafatto_occasion_icon'       => array( 'string', 'sarafatto_sanitize_term_icon' ),
			'sarafatto_occasion_image'      => array( 'integer', 'sarafatto_sanitize_term_image_id' ),
			'sarafatto_occasion_title'      => array( 'string', 'sanitize_text_field' ),
			'sarafatto_occasion_intro'      => array( 'string', 'sarafatto_sanitize_term_intro' ),
			'sarafatto_occasion_start_date' => array( 'string', 'sarafatto_sanitize_term_date' ),
			'sarafatto_occasion_end_date'   => array( 'string', 'sarafatto_sanitize_term_date' ),
		),
		'sarafatto_idea_regalo' => array(
			'sarafatto_idea_regalo_icon'        => array( 'string', 'sarafatto_sanitize_term_icon' ),
			'sarafatto_idea_regalo_image'       => array( 'integer', 'sarafatto_sanitize_term_image_id' ),
			'sarafatto_idea_regalo_title'       => array( 'string', 'sanitize_text_field' ),
			'sarafatto_idea_regalo_intro'       => array( 'string', 'sarafatto_sanitize_term_intro' ),
			'sarafatto_idea_regalo_description' => array( 'string', 'sarafatto_sanitize_gift_idea_description' ),
		),
	);

	foreach ( $term_meta as $taxonomy => $fields ) {
		foreach ( $fields as $meta_key => $field ) {
			register_term_meta(
				$taxonomy,
				$meta_key,
				array(
					'type'              => $field[0],
					'single'            => true,
					'sanitize_callback' => $field[1],
					'auth_callback'     => 'sarafatto_can_edit_term_meta',
				)
			);
		}
	}
}
add_action( 'init', 'sarafatto_register_term_meta', 20 );

function sarafatto_can_edit_term_meta( $allowed, $meta_key, $term_id ) {
	return current_user_can( 'manage_categories' );
}

function sarafatto_sanitize_term_icon( $value ) {
	$value = is_scalar( $value ) ? sanitize_key( (string) $value ) : '';
	$icons = sarafatto_get_editorial_icons();

	return isset( $icons[ $value ] ) ? $value : '';
}

function sarafatto_sanitize_term_image_id( $value ) {
	$image_id = is_scalar( $value ) ? absint( $value ) : 0;
	return $image_id && wp_attachment_is_image( $image_id ) ? $image_id : 0;
}

function sarafatto_sanitize_term_intro( $value ) {
	return sanitize_textarea_field( is_scalar( $value ) ? (string) $value : '' );
}

/** Allow safe editorial markup in the optional gift-idea description. */
function sarafatto_sanitize_gift_idea_description( $value ) {
	return wp_kses_post( is_scalar( $value ) ? (string) $value : '' );
}

/** Return a validated gift-idea icon slug, or an empty string. */
function sarafatto_get_gift_idea_icon( $term_id ) {
	$term = get_term( absint( $term_id ), 'sarafatto_idea_regalo' );
	return $term instanceof WP_Term ? sarafatto_sanitize_term_icon( get_term_meta( $term->term_id, 'sarafatto_idea_regalo_icon', true ) ) : '';
}

/** Return a gift-idea image attachment ID, or zero. */
function sarafatto_get_gift_idea_image_id( $term_id ) {
	$term = get_term( absint( $term_id ), 'sarafatto_idea_regalo' );
	return $term instanceof WP_Term ? sarafatto_sanitize_term_image_id( get_term_meta( $term->term_id, 'sarafatto_idea_regalo_image', true ) ) : 0;
}

/** Return an editorial title when set, falling back to the term name. */
function sarafatto_get_gift_idea_display_title( $term_id ) {
	$term = get_term( absint( $term_id ), 'sarafatto_idea_regalo' );
	if ( ! $term instanceof WP_Term ) {
		return '';
	}

	$title = get_term_meta( $term->term_id, 'sarafatto_idea_regalo_title', true );
	return is_string( $title ) && '' !== trim( $title ) ? $title : $term->name;
}

function sarafatto_sanitize_term_date( $value ) {
	$value = is_scalar( $value ) ? sanitize_text_field( (string) $value ) : '';
	return sarafatto_is_valid_calendar_date( $value ) ? $value : '';
}

function sarafatto_render_term_icon_field( $taxonomy, $term_id = 0, $show_label = true, $required = false ) {
	$meta_key = 'sarafatto_occasione' === $taxonomy ? 'sarafatto_occasion_icon' : 'sarafatto_idea_regalo_icon';
	$current  = $term_id ? get_term_meta( $term_id, $meta_key, true ) : '';
	$icons    = sarafatto_get_editorial_icons();
	?>
	<?php if ( $show_label ) : ?><label for="sarafatto-editorial-icon-<?php echo esc_attr( $taxonomy ); ?>"><?php esc_html_e( 'Icona', 'sarafatto-core' ); ?></label><?php endif; ?>
	<select id="sarafatto-editorial-icon-<?php echo esc_attr( $taxonomy ); ?>" name="<?php echo esc_attr( $meta_key ); ?>" class="sarafatto-editorial-icon-select" <?php echo $required ? 'required' : ''; ?>>
		<option value=""><?php esc_html_e( 'Nessuna icona', 'sarafatto-core' ); ?></option>
		<?php foreach ( $icons as $slug => $label ) : ?>
			<option value="<?php echo esc_attr( $slug ); ?>" <?php selected( $current, $slug ); ?>><?php echo esc_html( $label ); ?></option>
		<?php endforeach; ?>
	</select>
	<span class="sarafatto-editorial-icon-preview" data-sprite-url="<?php echo esc_url( SARAFATTO_CORE_URL . 'assets/icons/editorial-icons.svg' ); ?>" aria-hidden="true">
		<?php echo sarafatto_get_term_icon_markup( $current ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- generated from the fixed SVG sprite and a whitelisted symbol ID. ?>
	</span>
	<p class="description"><?php esc_html_e( 'Scegli un’icona dal set Saràfatto.', 'sarafatto-core' ); ?></p>
	<?php
}

function sarafatto_render_occasion_add_fields() {
	wp_nonce_field( 'sarafatto_save_editorial_term_meta', 'sarafatto_editorial_term_nonce' );
	?>
	<div class="form-field sarafatto-term-icon-field">
		<?php sarafatto_render_term_icon_field( 'sarafatto_occasione' ); ?>
	</div>
	<div class="form-field sarafatto-term-image-field">
		<label for="sarafatto-occasion-image"><?php esc_html_e( 'Immagine editoriale', 'sarafatto-core' ); ?></label>
		<input type="hidden" id="sarafatto-occasion-image" name="sarafatto_occasion_image" value="0">
		<div class="sarafatto-term-image-preview"></div>
		<button type="button" class="button sarafatto-term-image-select"><?php esc_html_e( 'Scegli immagine', 'sarafatto-core' ); ?></button>
		<button type="button" class="button-link-delete sarafatto-term-image-remove" hidden><?php esc_html_e( 'Rimuovi immagine', 'sarafatto-core' ); ?></button>
	</div>
	<div class="form-field"><label for="sarafatto-occasion-title"><?php esc_html_e( 'Titolo editoriale (facoltativo)', 'sarafatto-core' ); ?></label><input type="text" id="sarafatto-occasion-title" name="sarafatto_occasion_title"></div>
	<div class="form-field"><label for="sarafatto-occasion-intro"><?php esc_html_e( 'Breve testo / introduzione', 'sarafatto-core' ); ?></label><textarea id="sarafatto-occasion-intro" name="sarafatto_occasion_intro" rows="4"></textarea></div>
	<div class="form-field"><label for="sarafatto-occasion-start-date"><?php esc_html_e( 'Data inizio', 'sarafatto-core' ); ?></label><input type="date" id="sarafatto-occasion-start-date" name="sarafatto_occasion_start_date"></div>
	<div class="form-field"><label for="sarafatto-occasion-end-date"><?php esc_html_e( 'Data fine', 'sarafatto-core' ); ?></label><input type="date" id="sarafatto-occasion-end-date" name="sarafatto_occasion_end_date"></div>
	<p class="description"><?php esc_html_e( 'Per essere attiva in Home, l’occasione deve avere entrambe le date valide.', 'sarafatto-core' ); ?></p>
	<?php
}
add_action( 'sarafatto_occasione_add_form_fields', 'sarafatto_render_occasion_add_fields' );

function sarafatto_render_occasion_edit_fields( $term, $taxonomy ) {
	wp_nonce_field( 'sarafatto_save_editorial_term_meta', 'sarafatto_editorial_term_nonce' );
	$image_id  = absint( get_term_meta( $term->term_id, 'sarafatto_occasion_image', true ) );
	$image     = $image_id ? wp_get_attachment_image( $image_id, 'thumbnail', false, array( 'alt' => '' ) ) : '';
	$start     = get_term_meta( $term->term_id, 'sarafatto_occasion_start_date', true );
	$end       = get_term_meta( $term->term_id, 'sarafatto_occasion_end_date', true );
	$title     = get_term_meta( $term->term_id, 'sarafatto_occasion_title', true );
	$intro     = get_term_meta( $term->term_id, 'sarafatto_occasion_intro', true );
	?>
	<tr class="form-field"><th scope="row"><label for="sarafatto-editorial-icon-<?php echo esc_attr( $taxonomy ); ?>"><?php esc_html_e( 'Icona', 'sarafatto-core' ); ?></label></th><td><?php sarafatto_render_term_icon_field( $taxonomy, $term->term_id, false ); ?></td></tr>
	<tr class="form-field">
		<th scope="row"><label for="sarafatto-occasion-image"><?php esc_html_e( 'Immagine editoriale', 'sarafatto-core' ); ?></label></th>
		<td>
			<input type="hidden" id="sarafatto-occasion-image" name="sarafatto_occasion_image" value="<?php echo esc_attr( $image_id ); ?>">
			<div class="sarafatto-term-image-preview"><?php echo $image; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- generated by wp_get_attachment_image(). ?></div>
			<button type="button" class="button sarafatto-term-image-select"><?php esc_html_e( 'Scegli immagine', 'sarafatto-core' ); ?></button>
			<button type="button" class="button-link-delete sarafatto-term-image-remove" <?php echo $image ? '' : 'hidden'; ?>><?php esc_html_e( 'Rimuovi immagine', 'sarafatto-core' ); ?></button>
		</td>
	</tr>
	<tr class="form-field"><th scope="row"><label for="sarafatto-occasion-title"><?php esc_html_e( 'Titolo editoriale (facoltativo)', 'sarafatto-core' ); ?></label></th><td><input type="text" id="sarafatto-occasion-title" name="sarafatto_occasion_title" value="<?php echo esc_attr( is_scalar( $title ) ? $title : '' ); ?>"></td></tr>
	<tr class="form-field"><th scope="row"><label for="sarafatto-occasion-intro"><?php esc_html_e( 'Breve testo / introduzione', 'sarafatto-core' ); ?></label></th><td><textarea id="sarafatto-occasion-intro" name="sarafatto_occasion_intro" rows="4"><?php echo esc_textarea( is_scalar( $intro ) ? $intro : '' ); ?></textarea></td></tr>
	<tr class="form-field"><th scope="row"><label for="sarafatto-occasion-start-date"><?php esc_html_e( 'Data inizio', 'sarafatto-core' ); ?></label></th><td><input type="date" id="sarafatto-occasion-start-date" name="sarafatto_occasion_start_date" value="<?php echo esc_attr( is_scalar( $start ) ? $start : '' ); ?>"></td></tr>
	<tr class="form-field"><th scope="row"><label for="sarafatto-occasion-end-date"><?php esc_html_e( 'Data fine', 'sarafatto-core' ); ?></label></th><td><input type="date" id="sarafatto-occasion-end-date" name="sarafatto_occasion_end_date" value="<?php echo esc_attr( is_scalar( $end ) ? $end : '' ); ?>"></td></tr>
	<tr class="form-field"><th></th><td><p class="description"><?php esc_html_e( 'Le date sono facoltative; senza entrambe le date valide, l’occasione non è attiva in Home.', 'sarafatto-core' ); ?></p><?php sarafatto_render_occasion_date_warning( $start, $end ); ?></td></tr>
	<?php
}
add_action( 'sarafatto_occasione_edit_form_fields', 'sarafatto_render_occasion_edit_fields', 10, 2 );

function sarafatto_render_gift_idea_add_fields() {
	wp_nonce_field( 'sarafatto_save_editorial_term_meta', 'sarafatto_editorial_term_nonce' );
	?>
	<div class="form-field sarafatto-term-icon-field">
		<?php sarafatto_render_term_icon_field( 'sarafatto_idea_regalo', 0, true, true ); ?>
	</div>
	<div class="form-field sarafatto-term-image-field">
		<label for="sarafatto-gift-idea-image"><?php esc_html_e( 'Immagine editoriale', 'sarafatto-core' ); ?></label>
		<input type="hidden" id="sarafatto-gift-idea-image" name="sarafatto_idea_regalo_image" value="0">
		<div class="sarafatto-term-image-preview"></div>
		<button type="button" class="button sarafatto-term-image-select"><?php esc_html_e( 'Scegli immagine', 'sarafatto-core' ); ?></button>
		<button type="button" class="button-link-delete sarafatto-term-image-remove" hidden><?php esc_html_e( 'Rimuovi immagine', 'sarafatto-core' ); ?></button>
	</div>
	<div class="form-field"><label for="sarafatto-gift-idea-title"><?php esc_html_e( 'Titolo editoriale (facoltativo)', 'sarafatto-core' ); ?></label><input type="text" id="sarafatto-gift-idea-title" name="sarafatto_idea_regalo_title"></div>
	<div class="form-field"><label for="sarafatto-gift-idea-intro"><?php esc_html_e( 'Breve introduzione', 'sarafatto-core' ); ?></label><textarea id="sarafatto-gift-idea-intro" name="sarafatto_idea_regalo_intro" rows="4"></textarea></div>
	<div class="form-field"><label for="sarafatto-gift-idea-description"><?php esc_html_e( 'Descrizione estesa (facoltativa)', 'sarafatto-core' ); ?></label><textarea id="sarafatto-gift-idea-description" name="sarafatto_idea_regalo_description" rows="8" aria-describedby="sarafatto-gift-idea-description-help"></textarea><p class="description" id="sarafatto-gift-idea-description-help"><?php esc_html_e( 'Puoi usare paragrafi, grassetto, corsivo, link ed elenchi. Il markup non sicuro viene rimosso.', 'sarafatto-core' ); ?></p></div>
	<?php
}
add_action( 'sarafatto_idea_regalo_add_form_fields', 'sarafatto_render_gift_idea_add_fields' );

function sarafatto_render_gift_idea_edit_fields( $term, $taxonomy ) {
	wp_nonce_field( 'sarafatto_save_editorial_term_meta', 'sarafatto_editorial_term_nonce' );
	$image_id = sarafatto_get_gift_idea_image_id( $term->term_id );
	$image    = $image_id ? wp_get_attachment_image( $image_id, 'thumbnail', false, array( 'alt' => '' ) ) : '';
	$title    = get_term_meta( $term->term_id, 'sarafatto_idea_regalo_title', true );
	$intro    = get_term_meta( $term->term_id, 'sarafatto_idea_regalo_intro', true );
	$description = get_term_meta( $term->term_id, 'sarafatto_idea_regalo_description', true );
	?>
	<tr class="form-field"><th scope="row"><label for="sarafatto-editorial-icon-<?php echo esc_attr( $taxonomy ); ?>"><?php esc_html_e( 'Icona', 'sarafatto-core' ); ?></label></th><td><?php sarafatto_render_term_icon_field( $taxonomy, $term->term_id, false, true ); ?></td></tr>
	<tr class="form-field sarafatto-term-image-field"><th scope="row"><label for="sarafatto-gift-idea-image"><?php esc_html_e( 'Immagine editoriale', 'sarafatto-core' ); ?></label></th><td><input type="hidden" id="sarafatto-gift-idea-image" name="sarafatto_idea_regalo_image" value="<?php echo esc_attr( $image_id ); ?>"><div class="sarafatto-term-image-preview"><?php echo $image; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- generated by wp_get_attachment_image(). ?></div><button type="button" class="button sarafatto-term-image-select"><?php esc_html_e( 'Scegli immagine', 'sarafatto-core' ); ?></button><button type="button" class="button-link-delete sarafatto-term-image-remove" <?php echo $image ? '' : 'hidden'; ?>><?php esc_html_e( 'Rimuovi immagine', 'sarafatto-core' ); ?></button></td></tr>
	<tr class="form-field"><th scope="row"><label for="sarafatto-gift-idea-title"><?php esc_html_e( 'Titolo editoriale (facoltativo)', 'sarafatto-core' ); ?></label></th><td><input class="regular-text" type="text" id="sarafatto-gift-idea-title" name="sarafatto_idea_regalo_title" value="<?php echo esc_attr( is_scalar( $title ) ? $title : '' ); ?>"></td></tr>
	<tr class="form-field"><th scope="row"><label for="sarafatto-gift-idea-intro"><?php esc_html_e( 'Breve introduzione', 'sarafatto-core' ); ?></label></th><td><textarea class="large-text" id="sarafatto-gift-idea-intro" name="sarafatto_idea_regalo_intro" rows="4"><?php echo esc_textarea( is_scalar( $intro ) ? $intro : '' ); ?></textarea></td></tr>
	<tr class="form-field"><th scope="row"><label for="sarafatto-gift-idea-description"><?php esc_html_e( 'Descrizione estesa (facoltativa)', 'sarafatto-core' ); ?></label></th><td><textarea class="large-text" id="sarafatto-gift-idea-description" name="sarafatto_idea_regalo_description" rows="8" aria-describedby="sarafatto-gift-idea-description-help"><?php echo esc_textarea( is_scalar( $description ) ? $description : '' ); ?></textarea><p class="description" id="sarafatto-gift-idea-description-help"><?php esc_html_e( 'Puoi usare paragrafi, grassetto, corsivo, link ed elenchi. Il markup non sicuro viene rimosso.', 'sarafatto-core' ); ?></p></td></tr>
	<?php
}
add_action( 'sarafatto_idea_regalo_edit_form_fields', 'sarafatto_render_gift_idea_edit_fields', 10, 2 );

function sarafatto_render_occasion_date_warning( $start, $end ) {
	$start = is_scalar( $start ) ? (string) $start : '';
	$end   = is_scalar( $end ) ? (string) $end : '';
	if ( ( '' !== $start && ! sarafatto_is_valid_calendar_date( $start ) ) || ( '' !== $end && ! sarafatto_is_valid_calendar_date( $end ) ) || ( '' !== $start && '' !== $end && $start > $end ) ) {
		esc_html_e( 'Controlla il periodo: le date devono essere valide, entrambe presenti e in ordine.', 'sarafatto-core' );
	}
}

function sarafatto_save_occasion_term_meta( $term_id ) {
	if ( ! sarafatto_can_save_editorial_term_meta( $term_id ) ) {
		return;
	}

	$icon = sarafatto_sanitize_term_icon( sarafatto_term_post_value( 'sarafatto_occasion_icon' ) );
	$image_id = sarafatto_sanitize_term_image_id( sarafatto_term_post_value( 'sarafatto_occasion_image' ) );
	$title = sanitize_text_field( sarafatto_term_post_value( 'sarafatto_occasion_title' ) );
	$intro = sanitize_textarea_field( sarafatto_term_post_value( 'sarafatto_occasion_intro' ) );
	$raw_start = sarafatto_term_post_value( 'sarafatto_occasion_start_date' );
	$raw_end   = sarafatto_term_post_value( 'sarafatto_occasion_end_date' );
	$start     = sarafatto_sanitize_term_date( $raw_start );
	$end       = sarafatto_sanitize_term_date( $raw_end );

	if ( ( '' !== $raw_start && '' === $start ) || ( '' !== $raw_end && '' === $end ) || ( '' !== $start && '' !== $end && $start > $end ) || ( ( '' !== $start ) xor ( '' !== $end ) ) ) {
		set_transient( 'sarafatto_invalid_occasion_dates_' . get_current_user_id(), 1, MINUTE_IN_SECONDS );
	}

	update_term_meta( $term_id, 'sarafatto_occasion_icon', $icon );
	update_term_meta( $term_id, 'sarafatto_occasion_image', $image_id );
	update_term_meta( $term_id, 'sarafatto_occasion_title', $title );
	update_term_meta( $term_id, 'sarafatto_occasion_intro', $intro );
	update_term_meta( $term_id, 'sarafatto_occasion_start_date', $start );
	update_term_meta( $term_id, 'sarafatto_occasion_end_date', $end );
}
add_action( 'created_sarafatto_occasione', 'sarafatto_save_occasion_term_meta' );
add_action( 'edited_sarafatto_occasione', 'sarafatto_save_occasion_term_meta' );

function sarafatto_save_gift_idea_term_meta( $term_id ) {
	if ( ! sarafatto_can_save_editorial_term_meta( $term_id ) ) {
		return;
	}

	$icon = sarafatto_sanitize_term_icon( sarafatto_term_post_value( 'sarafatto_idea_regalo_icon' ) );
	if ( '' === $icon ) {
		set_transient( 'sarafatto_missing_gift_idea_icon_' . get_current_user_id(), 1, MINUTE_IN_SECONDS );
		return;
	}
	$image_id = sarafatto_sanitize_term_image_id( sarafatto_term_post_value( 'sarafatto_idea_regalo_image' ) );
	$title = sanitize_text_field( sarafatto_term_post_value( 'sarafatto_idea_regalo_title' ) );
	$intro = sanitize_textarea_field( sarafatto_term_post_value( 'sarafatto_idea_regalo_intro' ) );
	$raw_description = isset( $_POST['sarafatto_idea_regalo_description'] ) && is_scalar( $_POST['sarafatto_idea_regalo_description'] ) ? wp_kses_post( wp_unslash( $_POST['sarafatto_idea_regalo_description'] ) ) : '';
	$description = sarafatto_sanitize_gift_idea_description( $raw_description );
	update_term_meta( $term_id, 'sarafatto_idea_regalo_icon', $icon );
	update_term_meta( $term_id, 'sarafatto_idea_regalo_image', $image_id );
	update_term_meta( $term_id, 'sarafatto_idea_regalo_title', $title );
	update_term_meta( $term_id, 'sarafatto_idea_regalo_intro', $intro );
	update_term_meta( $term_id, 'sarafatto_idea_regalo_description', $description );
}
add_action( 'created_sarafatto_idea_regalo', 'sarafatto_save_gift_idea_term_meta' );
add_action( 'edited_sarafatto_idea_regalo', 'sarafatto_save_gift_idea_term_meta' );

function sarafatto_term_post_value( $key ) {
	return isset( $_POST[ $key ] ) && is_scalar( $_POST[ $key ] ) ? sanitize_text_field( wp_unslash( $_POST[ $key ] ) ) : '';
}

function sarafatto_can_save_editorial_term_meta( $term_id ) {
	$nonce = isset( $_POST['sarafatto_editorial_term_nonce'] ) && is_scalar( $_POST['sarafatto_editorial_term_nonce'] )
		? sanitize_text_field( wp_unslash( $_POST['sarafatto_editorial_term_nonce'] ) )
		: '';
	return $nonce && wp_verify_nonce( $nonce, 'sarafatto_save_editorial_term_meta' ) && current_user_can( 'manage_categories' );
}

function sarafatto_editorial_term_date_notice() {
	$screen = get_current_screen();
	$user_id = get_current_user_id();
	$key     = 'sarafatto_invalid_occasion_dates_' . $user_id;
	if ( ! $screen || 'sarafatto_occasione' !== $screen->taxonomy || ! get_transient( $key ) ) {
		return;
	}
	delete_transient( $key );
	?>
	<div class="notice notice-error is-dismissible"><p><?php esc_html_e( 'Le date dell’occasione non sono state accettate: inserisci un periodo valido con data iniziale non successiva alla data finale.', 'sarafatto-core' ); ?></p></div>
	<?php
}
add_action( 'admin_notices', 'sarafatto_editorial_term_date_notice' );

function sarafatto_gift_idea_icon_notice() {
	$screen = get_current_screen();
	$key = 'sarafatto_missing_gift_idea_icon_' . get_current_user_id();
	if ( ! $screen || 'sarafatto_idea_regalo' !== $screen->taxonomy || ! get_transient( $key ) ) {
		return;
	}
	delete_transient( $key );
	?>
	<div class="notice notice-error is-dismissible"><p><?php esc_html_e( 'Seleziona un’icona valida per l’Idea regalo. Gli altri campi non sono stati aggiornati.', 'sarafatto-core' ); ?></p></div>
	<?php
}
add_action( 'admin_notices', 'sarafatto_gift_idea_icon_notice' );

/** Load the term image and icon controls only on the two taxonomy screens. */
function sarafatto_enqueue_term_meta_admin_assets() {
	$screen = get_current_screen();
	if ( ! $screen || ! in_array( $screen->taxonomy, array( 'sarafatto_occasione', 'sarafatto_idea_regalo' ), true ) ) {
		return;
	}

	wp_enqueue_style( 'sarafatto-term-meta', SARAFATTO_CORE_URL . 'assets/css/term-meta.css', array(), SARAFATTO_CORE_VERSION );
	wp_enqueue_script( 'sarafatto-term-meta', SARAFATTO_CORE_URL . 'assets/js/term-meta.js', array( 'jquery' ), SARAFATTO_CORE_VERSION, true );
	wp_localize_script(
		'sarafatto-term-meta',
		'sarafattoTermMeta',
		array(
			'spriteUrl' => SARAFATTO_CORE_URL . 'assets/icons/editorial-icons.svg',
			'messages'  => array(
				'selectImage' => __( 'Scegli immagine editoriale', 'sarafatto-core' ),
				'useImage'    => __( 'Usa questa immagine', 'sarafatto-core' ),
			),
		)
	);
	if ( in_array( $screen->taxonomy, array( 'sarafatto_occasione', 'sarafatto_idea_regalo' ), true ) ) {
		wp_enqueue_media();
	}
}
add_action( 'admin_enqueue_scripts', 'sarafatto_enqueue_term_meta_admin_assets' );
