<?php
/** Accessors and admin media selector for the Home Personalizzati service. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Return translated defaults plus the configured Home service content. */
function sarafatto_get_home_personalized_content() {
	$defaults = array(
		'eyebrow' => sarafatto_theme_label( 'PERSONALIZZATI', 'PERSONALISED' ),
		'title'   => sarafatto_theme_label( "Hai qualcosa\nda dire?", "Something\nto say?" ),
		'lead'    => sarafatto_theme_label( 'Se non lo trovi tra i miei prodotti,\npossiamo personalizzarlo insieme.', 'If you can’t find it among my products,\nwe can personalise it together.' ),
		'body'    => sarafatto_theme_label( 'Frasi, parole, piccoli regali e oggetti da rendere più tuoi.\nMi racconti l’idea, ti dico cosa si può fare e su quali prodotti.', 'Words, phrases, little gifts and objects made more personal.\nTell me your idea and I’ll let you know what’s possible and which products can be customised.' ),
		'tags'    => sarafatto_theme_label( 'Tazze, Pochette, Shopper, Felpe', 'Mugs, Pouches, Tote bags, Sweatshirts' ),
		'cta'     => sarafatto_theme_label( 'Scopri come funziona', 'Discover how it works' ),
	);

	$get_text = static function ( $key, $default ) {
		$value = sarafatto_get_setting( $key, '' );
		return is_string( $value ) && '' !== trim( $value ) ? $value : $default;
	};
	$content = array(
		'eyebrow'  => $get_text( 'home_personalized_eyebrow', $defaults['eyebrow'] ),
		'title'    => $get_text( 'home_personalized_title', $defaults['title'] ),
		'lead'     => $get_text( 'home_personalized_lead', $defaults['lead'] ),
		'body'     => $get_text( 'home_personalized_body', $defaults['body'] ),
		'tags'     => $get_text( 'home_personalized_tags', $defaults['tags'] ),
		'cta'      => $get_text( 'home_personalized_cta_label', $defaults['cta'] ),
		'image_id' => absint( sarafatto_get_setting( 'home_personalized_image_id', 0 ) ),
		'page'     => sarafatto_get_linked_page( 'personalizzati' ),
	);

	$content['tags'] = array_values(
		array_unique(
			array_filter(
				array_map( 'sanitize_text_field', preg_split( '/[,\r\n]+/', (string) $content['tags'] ) ),
				static function ( $tag ) {
					return '' !== trim( $tag );
				}
			)
		)
	);

	return $content;
}

/** Load the WordPress media frame only on the Saràfatto settings page. */
function sarafatto_enqueue_home_personalized_admin_assets( $hook_suffix ) {
	if ( 'sarafatto_page_sarafatto-settings' !== $hook_suffix ) {
		return;
	}

	wp_enqueue_media();
	wp_enqueue_script(
		'sarafatto-home-personalized-admin',
		SARAFATTO_CORE_URL . 'assets/js/home-personalized-admin.js',
		array(),
		SARAFATTO_CORE_VERSION,
		true
	);
	wp_localize_script(
		'sarafatto-home-personalized-admin',
		'sarafattoHomePersonalizedMedia',
		array(
			'title'       => __( 'Seleziona l’immagine del servizio', 'sarafatto-core' ),
			'useImage'    => __( 'Usa questa immagine', 'sarafatto-core' ),
			'selectLabel' => __( 'Seleziona immagine', 'sarafatto-core' ),
			'replaceLabel'=> __( 'Cambia immagine', 'sarafatto-core' ),
		)
	);
}
add_action( 'admin_enqueue_scripts', 'sarafatto_enqueue_home_personalized_admin_assets' );
