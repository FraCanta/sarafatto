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
		array( 'page_negozio', __( 'Il negozio', 'sarafatto-core' ), 'page', 'pages' ),
		array( 'page_idee_regalo', __( 'Idee regalo', 'sarafatto-core' ), 'page', 'pages' ),
		array( 'page_personalizzati', __( 'Personalizzati', 'sarafatto-core' ), 'page', 'pages' ),
		array( 'page_spedizioni', __( 'Spedizioni', 'sarafatto-core' ), 'page', 'pages' ),
		array( 'page_contatti', __( 'Contatti', 'sarafatto-core' ), 'page', 'pages' ),
	);

	foreach ( $fields as $field ) {
		list( $key, $label, $type, $section ) = $field;
		add_settings_field(
			'sarafatto_' . $key,
			$label,
			'sarafatto_render_setting_field',
			'sarafatto-settings',
			'sarafatto_' . $section,
			array( 'key' => $key, 'type' => $type )
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
	$name  = 'sarafatto_settings[' . $key . ']';
	$id    = 'sarafatto-setting-' . $key;

	if ( 'textarea' === $type ) {
		printf( '<textarea class="large-text" id="%1$s" name="%2$s" rows="5">%3$s</textarea>', esc_attr( $id ), esc_attr( $name ), esc_textarea( $value ) );
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
		printf( '<input class="regular-text" type="%1$s" id="%2$s" name="%3$s" value="%4$s">', esc_attr( $type ), esc_attr( $id ), esc_attr( $name ), esc_attr( $value ) );
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
		} elseif ( in_array( $key, array( 'orari', 'whatsapp_message', 'shipping_text' ), true ) ) {
			$clean[ $key ] = sanitize_textarea_field( $value );
		} else {
			$clean[ $key ] = sanitize_text_field( $value );
		}
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
