<?php
/** Register and render the Saràfatto settings page with the Settings API. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_register_settings() {
	register_setting(
		'sarafatto_settings_group',
		'sarafatto_settings',
		array(
			'type'              => 'array',
			'sanitize_callback' => 'sarafatto_sanitize_settings',
			'default'           => array(),
		)
	);

	$sections = array(
		'contacts' => __( 'Contatti', 'sarafatto-core' ),
		'hours'    => __( 'Orari', 'sarafatto-core' ),
		'social'   => __( 'Social', 'sarafatto-core' ),
		'whatsapp' => __( 'WhatsApp', 'sarafatto-core' ),
		'shipping' => __( 'Spedizioni', 'sarafatto-core' ),
		'pages'    => __( 'Pagine collegate', 'sarafatto-core' ),
		'home_personalized' => __( 'Servizio Personalizzati', 'sarafatto-core' ),
	);

	foreach ( $sections as $section_id => $section_title ) {
		add_settings_section(
			'sarafatto_' . $section_id,
			$section_title,
			'__return_false',
			'sarafatto-settings'
		);
	}

	$fields = array(
		array( 'telefono', __( 'Telefono', 'sarafatto-core' ), 'tel', 'contacts' ),
		array( 'whatsapp', __( 'Numero WhatsApp', 'sarafatto-core' ), 'tel', 'contacts' ),
		array( 'email', __( 'Email', 'sarafatto-core' ), 'email', 'contacts' ),
		array( 'indirizzo', __( 'Indirizzo', 'sarafatto-core' ), 'text', 'contacts' ),
		array( 'google_maps_url', __( 'URL Google Maps', 'sarafatto-core' ), 'url', 'contacts' ),
		array( 'orari', __( 'Orari di apertura', 'sarafatto-core' ), 'textarea', 'hours' ),
		array( 'social_instagram', __( 'Instagram', 'sarafatto-core' ), 'url', 'social' ),
		array( 'social_facebook', __( 'Facebook', 'sarafatto-core' ), 'url', 'social' ),
		array( 'social_tiktok', __( 'TikTok', 'sarafatto-core' ), 'url', 'social' ),
		array( 'social_pinterest', __( 'Pinterest', 'sarafatto-core' ), 'url', 'social' ),
		array( 'whatsapp_message', __( 'Messaggio predefinito', 'sarafatto-core' ), 'textarea', 'whatsapp' ),
		array( 'shipping_title', __( 'Titolo breve', 'sarafatto-core' ), 'text', 'shipping' ),
		array( 'shipping_text', __( 'Testo', 'sarafatto-core' ), 'textarea', 'shipping' ),
		array( 'shipping_zone', __( 'Zona di spedizione', 'sarafatto-core' ), 'text', 'shipping' ),
		array( 'home_personalized_eyebrow', __( 'Eyebrow', 'sarafatto-core' ), 'text', 'home_personalized', 'PERSONALIZZATI' ),
		array( 'home_personalized_title', __( 'Titolo', 'sarafatto-core' ), 'textarea', 'home_personalized', "Hai qualcosa\nda dire?" ),
		array( 'home_personalized_lead', __( 'Testo principale', 'sarafatto-core' ), 'textarea', 'home_personalized', "Se non lo trovi tra i miei prodotti,\npossiamo personalizzarlo insieme." ),
		array( 'home_personalized_body', __( 'Testo secondario', 'sarafatto-core' ), 'textarea', 'home_personalized', "Frasi, parole, piccoli regali e oggetti da rendere più tuoi.\nMi racconti l’idea, ti dico cosa si può fare e su quali prodotti." ),
		array( 'home_personalized_tags', __( 'Tipologie personalizzabili', 'sarafatto-core' ), 'textarea', 'home_personalized', 'Tazze, Pochette, Shopper, Felpe' ),
		array( 'home_personalized_image_id', __( 'Immagine', 'sarafatto-core' ), 'image', 'home_personalized' ),
		array( 'home_personalized_cta_label', __( 'Testo CTA', 'sarafatto-core' ), 'text', 'home_personalized', 'Scopri come funziona' ),
		array( 'page_personalizzati', __( 'Pagina CTA', 'sarafatto-core' ), 'page', 'home_personalized' ),
		array( 'page_negozio', __( 'Il negozio', 'sarafatto-core' ), 'page', 'pages' ),
		array( 'page_idee_regalo', __( 'Idee regalo', 'sarafatto-core' ), 'page', 'pages' ),
		array( 'page_spedizioni', __( 'Spedizioni', 'sarafatto-core' ), 'page', 'pages' ),
		array( 'page_contatti', __( 'Contatti', 'sarafatto-core' ), 'page', 'pages' ),
	);

	foreach ( $fields as $field ) {
		list( $key, $label, $type, $section ) = $field;
		$field_args = array( 'key' => $key, 'type' => $type );
		if ( isset( $field[4] ) ) {
			$field_args['placeholder'] = $field[4];
		}
		add_settings_field(
			'sarafatto_' . $key,
			$label,
			'sarafatto_render_setting_field',
			'sarafatto-settings',
			'sarafatto_' . $section,
			$field_args
		);
	}
}
add_action( 'admin_init', 'sarafatto_register_settings' );

/** Use the custom capability for options.php submissions from this settings group. */
function sarafatto_settings_option_capability() {
	return 'manage_sarafatto_settings';
}
add_filter( 'option_page_capability_sarafatto_settings_group', 'sarafatto_settings_option_capability' );

function sarafatto_register_settings_menu() {
	add_menu_page(
		__( 'Saràfatto', 'sarafatto-core' ),
		__( 'Saràfatto', 'sarafatto-core' ),
		'manage_sarafatto_settings',
		'sarafatto',
		'sarafatto_render_settings_page',
		'dashicons-store',
		58
	);
	add_submenu_page(
		'sarafatto',
		__( 'Impostazioni Saràfatto', 'sarafatto-core' ),
		__( 'Impostazioni', 'sarafatto-core' ),
		'manage_sarafatto_settings',
		'sarafatto-settings',
		'sarafatto_render_settings_page'
	);
	remove_submenu_page( 'sarafatto', 'sarafatto' );
}
add_action( 'admin_menu', 'sarafatto_register_settings_menu' );

function sarafatto_render_settings_page() {
	if ( ! current_user_can( 'manage_sarafatto_settings' ) ) {
		wp_die( esc_html__( 'Non hai i permessi per accedere a queste impostazioni.', 'sarafatto-core' ) );
	}
	?>
	<div class="wrap">
		<h1><?php esc_html_e( 'Impostazioni Saràfatto', 'sarafatto-core' ); ?></h1>
		<form action="options.php" method="post">
			<?php
			settings_fields( 'sarafatto_settings_group' );
			do_settings_sections( 'sarafatto-settings' );
			submit_button( __( 'Salva le impostazioni', 'sarafatto-core' ) );
			?>
		</form>
	</div>
	<?php
}

function sarafatto_render_setting_field( $args ) {
	$key   = $args['key'];
	$type  = $args['type'];
	$value = sarafatto_get_setting( $key, '' );
	$placeholder = isset( $args['placeholder'] ) ? (string) $args['placeholder'] : '';
	$name  = 'sarafatto_settings[' . $key . ']';
	$id    = 'sarafatto-setting-' . $key;

	if ( 'textarea' === $type ) {
		printf( '<textarea class="large-text" id="%1$s" name="%2$s" rows="5" placeholder="%4$s">%3$s</textarea>', esc_attr( $id ), esc_attr( $name ), esc_textarea( $value ), esc_attr( $placeholder ) );
	} elseif ( 'image' === $type ) {
		$image_id = absint( $value );
		printf( '<input type="hidden" id="%1$s" name="%2$s" value="%3$d">', esc_attr( $id ), esc_attr( $name ), $image_id );
		echo '<div class="sarafatto-home-personalized-image-preview" aria-live="polite">';
		if ( $image_id && wp_attachment_is_image( $image_id ) ) {
			echo wp_get_attachment_image( $image_id, 'medium', false, array( 'alt' => '' ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- Generated by wp_get_attachment_image().
		}
		echo '</div>';
		printf( '<button type="button" class="button sarafatto-home-personalized-image-select">%s</button> ', esc_html( $image_id ? __( 'Cambia immagine', 'sarafatto-core' ) : __( 'Seleziona immagine', 'sarafatto-core' ) ) );
		printf( '<button type="button" class="button sarafatto-home-personalized-image-remove"%s>%s</button>', $image_id ? '' : ' hidden', esc_html__( 'Rimuovi immagine', 'sarafatto-core' ) );
	} elseif ( 'page' === $type ) {
		$page_dropdown = wp_dropdown_pages(
			array(
				'name'                  => $name,
				'id'                    => $id,
				'selected'              => absint( $value ),
				'show_option_none'      => __( '— Nessuna pagina selezionata —', 'sarafatto-core' ),
				'option_none_value'     => 0,
				'post_status'           => 'publish',
				'echo'                  => 0,
			)
		);
		echo $page_dropdown; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped -- wp_dropdown_pages escapes its generated options.
	} else {
		printf( '<input class="regular-text" type="%1$s" id="%2$s" name="%3$s" value="%4$s" placeholder="%5$s">', esc_attr( $type ), esc_attr( $id ), esc_attr( $name ), esc_attr( $value ), esc_attr( $placeholder ) );
	}
}

/** Sanitize and whitelist the single structured settings option. */
function sarafatto_sanitize_settings( $input ) {
	$input = is_array( $input ) ? $input : array();
	$clean = array();
	$text_fields = array(
		'whatsapp'       => true,
		'email'          => true,
		'indirizzo'      => true,
		'google_maps_url'=> true,
		'orari'          => true,
		'social_instagram' => true,
		'social_facebook'  => true,
		'social_tiktok'    => true,
		'social_pinterest' => true,
		'whatsapp_message' => true,
		'shipping_title' => true,
		'shipping_text'  => true,
		'shipping_zone'  => true,
		'home_personalized_eyebrow' => true,
		'home_personalized_title'   => true,
		'home_personalized_lead'    => true,
		'home_personalized_body'    => true,
		'home_personalized_tags'    => true,
		'home_personalized_cta_label' => true,
	);

	if ( isset( $input['telefono'] ) ) {
		$clean['telefono'] = sanitize_text_field( is_scalar( $input['telefono'] ) ? (string) $input['telefono'] : '' );
	}
	foreach ( $text_fields as $key => $unused ) {
		if ( ! isset( $input[ $key ] ) ) {
			continue;
		}
		$value = is_scalar( $input[ $key ] ) ? (string) $input[ $key ] : '';
		if ( 'email' === $key ) {
			$clean[ $key ] = sanitize_email( $value );
		} elseif ( in_array( $key, array( 'google_maps_url', 'social_instagram', 'social_facebook', 'social_tiktok', 'social_pinterest' ), true ) ) {
			$clean[ $key ] = esc_url_raw( $value );
		} elseif ( in_array( $key, array( 'orari', 'whatsapp_message', 'shipping_text', 'home_personalized_title', 'home_personalized_lead', 'home_personalized_body', 'home_personalized_tags' ), true ) ) {
			$clean[ $key ] = sanitize_textarea_field( $value );
		} else {
			$clean[ $key ] = sanitize_text_field( $value );
		}
	}

	if ( isset( $input['home_personalized_image_id'] ) ) {
		$image_id = is_scalar( $input['home_personalized_image_id'] ) ? absint( $input['home_personalized_image_id'] ) : 0;
		$clean['home_personalized_image_id'] = $image_id && wp_attachment_is_image( $image_id ) ? $image_id : 0;
	}

	$page_roles = array( 'negozio', 'idee_regalo', 'personalizzati', 'spedizioni', 'contatti' );
	foreach ( $page_roles as $role ) {
		$key = 'page_' . $role;
		if ( isset( $input[ $key ] ) ) {
			$page_id       = is_scalar( $input[ $key ] ) ? absint( $input[ $key ] ) : 0;
			$page          = $page_id ? get_post( $page_id ) : null;
			$clean[ $key ] = $page instanceof WP_Post && 'page' === $page->post_type && 'publish' === $page->post_status ? $page_id : 0;
		}
	}

	return $clean;
}
