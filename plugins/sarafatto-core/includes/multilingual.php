<?php
/** Integrazione opzionale con Polylang e fallback sicuri in singola lingua. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_is_polylang_active() {
	return function_exists( 'pll_current_language' );
}

/** Restituisce la lingua corrente; senza Polylang usa l’italiano. */
function sarafatto_get_current_language() {
	if ( function_exists( 'pll_current_language' ) ) {
		$language = pll_current_language( 'slug' );
		if ( is_string( $language ) && '' !== $language ) {
			return sanitize_key( $language );
		}
	}

	return 'it';
}

/** Return the language-aware site home URL. */
function sarafatto_get_language_home_url( $language = '' ) {
	$language = '' !== $language ? sanitize_key( $language ) : sarafatto_get_current_language();
	if ( function_exists( 'pll_home_url' ) ) {
		return pll_home_url( $language );
	}

	return home_url( '/' );
}

/** Point the custom logo to the language home instead of its translated page permalink. */
function sarafatto_filter_custom_logo_home_url( $html ) {
	$home_url = sarafatto_get_language_home_url();
	if ( ! is_string( $html ) || '' === $html || '' === $home_url ) {
		return $html;
	}

	return preg_replace( '/href="[^"]*"/', 'href="' . esc_url( $home_url ) . '"', $html, 1 );
}
add_filter( 'get_custom_logo', 'sarafatto_filter_custom_logo_home_url' );

/** Aggiunge alle query il parametro `lang` documentato da Polylang, se attivo. */
function sarafatto_add_language_to_query_args( $args ) {
	$args = is_array( $args ) ? $args : array();
	if ( sarafatto_is_polylang_active() ) {
		$args['lang'] = sarafatto_get_current_language();
	}
	return $args;
}

/** Risolve la traduzione di un post o termine senza ripiegare su un’altra lingua. */
function sarafatto_get_translation_id( $object_id, $object_type, $language = '' ) {
	$object_id = absint( $object_id );
	$language  = '' !== $language ? sanitize_key( $language ) : sarafatto_get_current_language();
	if ( ! $object_id || ! in_array( $object_type, array( 'post', 'term' ), true ) ) {
		return 0;
	}

	if ( ! sarafatto_is_polylang_active() ) {
		return 'it' === $language ? $object_id : 0;
	}

	$translate = 'post' === $object_type ? 'pll_get_post' : 'pll_get_term';
	if ( ! function_exists( $translate ) ) {
		return 0;
	}

	$translation_id = absint( call_user_func( $translate, $object_id, $language ) );
	return $translation_id ? $translation_id : 0;
}

/** Keep product categories available to Polylang's term translation model. */
function sarafatto_polylang_register_product_category_taxonomy( $taxonomies, $is_settings = false ) {
	$taxonomies = is_array( $taxonomies ) ? $taxonomies : array();
	$taxonomies[] = 'sarafatto_categoria';
	$taxonomies[] = 'sarafatto_idea_regalo';

	return array_values( array_unique( $taxonomies ) );
}
add_filter( 'pll_get_taxonomies', 'sarafatto_polylang_register_product_category_taxonomy', 10, 2 );

/** Return a product category term in the requested language, or null if missing. */
function sarafatto_get_translated_category_term( $term_id, $language = '' ) {
	$term = get_term( absint( $term_id ), 'sarafatto_categoria' );
	if ( ! $term instanceof WP_Term ) {
		return null;
	}

	$translation_id = sarafatto_get_translation_id( $term->term_id, 'term', $language );
	if ( ! $translation_id ) {
		return null;
	}

	$translated_term = get_term( $translation_id, 'sarafatto_categoria' );
	return $translated_term instanceof WP_Term ? $translated_term : null;
}

/** Restituisce la URL della traduzione esistente oppure una stringa vuota. */
function sarafatto_get_translation_url( $object_id, $object_type, $language ) {
	$translation_id = sarafatto_get_translation_id( $object_id, $object_type, $language );
	if ( ! $translation_id ) {
		return '';
	}

	if ( 'post' === $object_type ) {
		$url = get_permalink( $translation_id );
		return is_string( $url ) ? $url : '';
	}

	$term = get_term( $translation_id );
	$url  = $term instanceof WP_Term ? get_term_link( $term ) : '';
	return is_wp_error( $url ) || ! is_string( $url ) ? '' : $url;
}

/** Verifica se una pagina è la Home configurata o una sua traduzione Polylang. */
function sarafatto_is_front_page_translation( $post_id ) {
	$post_id      = absint( $post_id );
	$front_page_id = sarafatto_get_front_page_id();
	if ( ! $post_id || ! $front_page_id ) {
		return false;
	}
	if ( $post_id === $front_page_id ) {
		return true;
	}

	if ( function_exists( 'pll_get_post_translations' ) ) {
		$translations = pll_get_post_translations( $front_page_id );
		return is_array( $translations ) && in_array( $post_id, array_map( 'absint', $translations ), true );
	}

	return false;
}

/** Build the translated URL for the shared product archive while retaining its configured archive path. */
function sarafatto_get_product_archive_language_url( $language ) {
	if ( ! function_exists( 'is_post_type_archive' ) || ! is_post_type_archive( 'sarafatto_prodotto' ) || ! function_exists( 'sarafatto_get_language_home_url' ) ) {
		return '';
	}

	$archive_url = get_post_type_archive_link( 'sarafatto_prodotto' );
	$current_url = sarafatto_get_language_home_url( sarafatto_get_current_language() );
	$target_url  = sarafatto_get_language_home_url( $language );
	$archive_path = is_string( $archive_url ) ? wp_parse_url( $archive_url, PHP_URL_PATH ) : '';
	$current_path = is_string( $current_url ) ? wp_parse_url( $current_url, PHP_URL_PATH ) : '';
	if ( ! is_string( $archive_path ) || ! is_string( $current_path ) || ! is_string( $target_url ) ) {
		return '';
	}

	$current_prefix = trailingslashit( untrailingslashit( $current_path ) );
	if ( '/' === $current_prefix ) {
		$current_prefix = '/';
	}
	if ( 0 !== strpos( $archive_path, $current_prefix ) ) {
		return '';
	}

	$archive_relative_path = ltrim( substr( $archive_path, strlen( $current_prefix ) ), '/' );
	return '' !== $archive_relative_path ? trailingslashit( $target_url ) . $archive_relative_path : '';
}

/** Prepara le opzioni linguistiche del selettore custom nel contesto corrente. */
function sarafatto_get_language_switcher_items() {
	if ( ! function_exists( 'pll_languages_list' ) || ! function_exists( 'pll_current_language' ) ) {
		return array();
	}

	$languages = pll_languages_list( array( 'fields' => 'slug' ) );
	if ( ! is_array( $languages ) || ! in_array( 'it', $languages, true ) || ! in_array( 'en', $languages, true ) ) {
		return array();
	}

	$current = sarafatto_get_current_language();
	if ( ! in_array( $current, array( 'it', 'en' ), true ) ) {
		return array();
	}

	$object_id   = 0;
	$object_type = '';
	$is_front_page_context = function_exists( 'is_front_page' ) && is_front_page();
	$is_product_archive = function_exists( 'is_post_type_archive' ) && is_post_type_archive( 'sarafatto_prodotto' );
	if ( is_singular() || is_front_page() ) {
		$object_id   = absint( get_queried_object_id() );
		$object_type = 'post';
		$language_front_page_id = absint( get_option( 'page_on_front' ) );
		if ( $object_id && $object_id === $language_front_page_id ) {
			$is_front_page_context = true;
		}
		if ( $object_id && function_exists( 'sarafatto_is_front_page_translation' ) ) {
			$is_front_page_context = $is_front_page_context || sarafatto_is_front_page_translation( $object_id );
		}
	} elseif ( is_tax() || is_category() || is_tag() ) {
		$object_id   = absint( get_queried_object_id() );
		$object_type = 'term';
	} elseif ( is_home() ) {
		$object_id = absint( get_option( 'page_for_posts' ) );
		if ( $object_id ) {
			$object_type = 'post';
		}
	}

	$items = array();
	foreach ( array( 'it' => 'IT', 'en' => 'EN' ) as $slug => $label ) {
		$url = '';
		if ( $current !== $slug ) {
			if ( $is_front_page_context ) {
				$url = sarafatto_get_language_home_url( $slug );
			} elseif ( $is_product_archive ) {
				$url = sarafatto_get_product_archive_language_url( $slug );
			} elseif ( $object_id ) {
				$url = sarafatto_get_translation_url( $object_id, $object_type, $slug );
			}
		}
		$items[] = array(
			'slug'    => $slug,
			'label'   => $label,
			'current' => $current === $slug,
			'url'     => $url,
		);
	}

	return $items;
}

/** Aggiunge i campi strutturali ai filtri di copia/sincronizzazione supportati da Polylang. */
function sarafatto_polylang_copy_product_meta( $metas, $sync = false, $from = 0, $to = 0, $lang = '' ) {
	$metas = is_array( $metas ) ? $metas : array();
	$product = get_post( absint( $from ) );
	if ( ! $product instanceof WP_Post || 'sarafatto_prodotto' !== $product->post_type ) {
		return $metas;
	}
	$metas = array_diff( $metas, array( 'sarafatto_price', 'sarafatto_sku' ) );
	if ( $sync ) {
		$metas = array_diff( $metas, array( 'sarafatto_editorial_label', 'sarafatto_story', 'sarafatto_gallery', '_thumbnail_id', 'sarafatto_materials', 'sarafatto_dimensions', 'sarafatto_colors', 'sarafatto_variants', 'sarafatto_care', 'sarafatto_customization_details', 'sarafatto_personalization_details' ) );
	}
	$metas = array_merge( $metas, array( 'sarafatto_is_new', 'sarafatto_is_featured', 'sarafatto_is_sold_out', 'sarafatto_personalizable', 'sarafatto_is_handmade' ) );
	if ( ! $sync ) {
		$metas = array_merge( $metas, array( '_thumbnail_id', 'sarafatto_gallery' ) );
	}
	$dummy_values = get_post_meta( $product->ID, 'sarafatto_dummy_details', true );
	$dummy_values = is_array( $dummy_values ) ? $dummy_values : array();
	$metas = array_diff( $metas, array( 'sarafatto_dummy_details', 'sarafatto_has_dummy_details' ) );
	if ( $dummy_values ) {
		$metas = array_diff( $metas, array_keys( $dummy_values ) );
	}
	return array_values( array_unique( $metas ) );
}
add_filter( 'pll_copy_post_metas', 'sarafatto_polylang_copy_product_meta', 10, 5 );

/** Copia/sincronizza i meta strutturali e copia le immagini solo alla creazione. */
function sarafatto_polylang_copy_term_meta( $metas, $sync = false, $from = 0, $to = 0, $lang = '' ) {
	$metas = is_array( $metas ) ? $metas : array();
	$term  = get_term( absint( $from ) );
	if ( ! $term instanceof WP_Term || ! in_array( $term->taxonomy, array( 'sarafatto_occasione', 'sarafatto_idea_regalo' ), true ) ) {
		return $metas;
	}
	if ( $sync ) {
		$metas = array_diff(
			$metas,
			array(
				'sarafatto_occasion_image',
				'sarafatto_occasion_title',
				'sarafatto_occasion_intro',
				'sarafatto_idea_regalo_image',
				'sarafatto_idea_regalo_title',
				'sarafatto_idea_regalo_intro',
				'sarafatto_idea_regalo_description',
			)
		);
	}
	$structural_metas = 'sarafatto_occasione' === $term->taxonomy
		? array( 'sarafatto_occasion_icon', 'sarafatto_occasion_start_date', 'sarafatto_occasion_end_date' )
		: array( 'sarafatto_idea_regalo_icon' );
	$metas = array_merge( $metas, $structural_metas );
	if ( ! $sync ) {
		$image_meta = 'sarafatto_occasione' === $term->taxonomy ? 'sarafatto_occasion_image' : 'sarafatto_idea_regalo_image';
		$metas[]    = $image_meta;
	}
	return array_values( array_unique( $metas ) );
}
add_filter( 'pll_copy_term_metas', 'sarafatto_polylang_copy_term_meta', 10, 5 );

/** Copia le tassonomie prodotto usando la mappatura dei termini tradotti. */
function sarafatto_polylang_copy_product_taxonomies( $taxonomies, $sync = false, $from = 0, $to = 0, $lang = '' ) {
	$taxonomies = is_array( $taxonomies ) ? $taxonomies : array();
	$product    = get_post( absint( $from ) );
	if ( ! $product instanceof WP_Post || 'sarafatto_prodotto' !== $product->post_type ) {
		return $taxonomies;
	}
	return array_values( array_unique( array_merge( $taxonomies, array( 'sarafatto_categoria', 'sarafatto_occasione', 'sarafatto_idea_regalo' ) ) ) );
}
add_filter( 'pll_copy_taxonomies', 'sarafatto_polylang_copy_product_taxonomies', 10, 5 );

/** Registra in String Translations i testi globali e il modello WhatsApp. */
function sarafatto_register_polylang_strings() {
	if ( ! function_exists( 'pll_register_string' ) ) {
		return;
	}

	$settings = get_option( 'sarafatto_settings', array() );
	$settings = is_array( $settings ) ? $settings : array();
	$strings  = array(
		'orari'            => true,
		'whatsapp_message' => true,
		'shipping_title'   => false,
		'shipping_text'    => true,
		'shipping_zone'    => false,
	);
	foreach ( $strings as $key => $multiline ) {
		if ( isset( $settings[ $key ] ) && is_scalar( $settings[ $key ] ) && '' !== (string) $settings[ $key ] ) {
			pll_register_string( 'sarafatto_' . $key, (string) $settings[ $key ], 'Saràfatto', $multiline );
		}
	}
	pll_register_string( 'sarafatto_product_whatsapp_template', 'Ciao! Vorrei avere qualche informazione su %s.', 'Saràfatto', false );
	pll_register_string( 'sarafatto_language_switcher_label', 'Lingua', 'Saràfatto', false );
	pll_register_string( 'sarafatto_translation_unavailable', 'traduzione non disponibile', 'Saràfatto', false );
}
add_action( 'admin_init', 'sarafatto_register_polylang_strings', 20 );

/** Restituisce una stringa dinamica tradotta quando Polylang è attivo. */
function sarafatto_translate_dynamic_string( $string ) {
	return is_string( $string ) && function_exists( 'pll__' ) ? pll__( $string ) : $string;
}

/** Genera il link WhatsApp per un prodotto nella lingua corrente. */
function sarafatto_get_product_whatsapp_url( $post_id ) {
	$product = get_post( absint( $post_id ) );
	if ( ! $product instanceof WP_Post || 'sarafatto_prodotto' !== $product->post_type ) {
		return '';
	}
	if ( sarafatto_is_polylang_active() && function_exists( 'pll_get_post' ) ) {
		$translated_id = sarafatto_get_translation_id( $product->ID, 'post', sarafatto_get_current_language() );
		if ( $translated_id ) {
			$product = get_post( $translated_id );
		} elseif ( function_exists( 'pll_get_post_language' ) && sarafatto_get_current_language() !== pll_get_post_language( $product->ID, 'slug' ) ) {
			return '';
		}
	}

	$template = sarafatto_translate_dynamic_string( 'Ciao! Vorrei avere qualche informazione su %s.' );
	return sarafatto_get_whatsapp_url( sprintf( $template, get_the_title( $product ) ) );
}
