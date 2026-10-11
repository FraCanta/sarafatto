<?php
/** Primary navigation and the editorial Products mega menu. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Return the current-language product archive URL. */
function sarafatto_get_products_archive_url() {
	$url = get_post_type_archive_link( 'sarafatto_prodotto' );
	return is_string( $url ) ? esc_url_raw( $url ) : '';
}

/** Compare menu URLs without allowing query or fragment differences to matter. */
function sarafatto_normalize_menu_url( $url ) {
	$url = is_string( $url ) ? trim( $url ) : '';
	if ( '' === $url ) {
		return '';
	}
	$parts = wp_parse_url( $url );
	if ( ! is_array( $parts ) ) {
		return untrailingslashit( $url );
	}
	$path = isset( $parts['path'] ) ? untrailingslashit( $parts['path'] ) : '';
	return strtolower( ( $parts['host'] ?? '' ) . $path );
}

/** Create the archive menu object when the configured menu has no Products item. */
function sarafatto_create_products_menu_item( $archive_url, $menu_order ) {
	$item_id = -1 * absint( crc32( 'sarafatto-products-archive' ) );
	if ( ! $item_id ) {
		$item_id = -1;
	}

	return (object) array(
		'ID'               => $item_id,
		'db_id'            => 0,
		'menu_item_parent' => 0,
		'object_id'        => 0,
		'object'           => 'sarafatto_prodotto',
		'type'             => 'post_type_archive',
		'type_label'       => sarafatto_theme_label( 'Archivio prodotti', 'Product archive' ),
		'title'            => sarafatto_theme_label( 'Prodotti', 'Products' ),
		'current'          => false,
		'url'              => $archive_url,
		'target'           => '',
		'attr_title'       => '',
		'description'      => '',
		'xfn'              => '',
		'menu_order'       => absint( $menu_order ),
		'classes'          => array(),
	);
}

/** Ensure Products occupies the former New arrivals position in the primary menu. */
function sarafatto_prepare_primary_navigation( $items, $args ) {
	if ( empty( $args->theme_location ) || 'primary' !== $args->theme_location || ! is_array( $items ) ) {
		return $items;
	}

	$archive_url = sarafatto_get_products_archive_url();
	if ( '' === $archive_url ) {
		return $items;
	}

	$archive_key = sarafatto_normalize_menu_url( $archive_url );
	$products_label = strtolower( trim( wp_strip_all_tags( sarafatto_theme_label( 'Prodotti', 'Products' ) ) ) );
	$news_url    = function_exists( 'sarafatto_get_home_news_url' ) ? sarafatto_get_home_news_url() : '';
	$news_key    = sarafatto_normalize_menu_url( $news_url );
	$product_index = null;
	$product_indexes = array();
	$news_index    = null;

	foreach ( $items as $index => $item ) {
		if ( ! is_object( $item ) || ! empty( $item->menu_item_parent ) ) {
			continue;
		}

		$item_title = strtolower( trim( wp_strip_all_tags( (string) ( $item->title ?? '' ) ) ) );
		$is_products = ( isset( $item->object ) && 'sarafatto_prodotto' === $item->object )
			|| ( isset( $item->url ) && $archive_key === sarafatto_normalize_menu_url( $item->url ) )
			|| $products_label === $item_title;
		if ( $is_products ) {
			$product_indexes[] = $index;
			if ( null === $product_index ) {
				$product_index = $index;
			}
		}

		if ( null !== $news_key && '' !== $news_key && isset( $item->url ) && $news_key === sarafatto_normalize_menu_url( $item->url ) ) {
			$news_index = $index;
		}
	}

	$insert_at = null !== $news_index ? $news_index : 0;
	$candidate_index = null !== $product_index ? $product_index : $news_index;
	$prepared  = array();
	$products  = null !== $candidate_index ? $items[ $candidate_index ] : null;
	$product_menu_items = array();
	$product_menu_descendant_ids = array();
	$product_menu_parent_ids = array();
	foreach ( $product_indexes as $products_index ) {
		$product_item = $items[ $products_index ];
		$product_menu_parent_ids = array_merge( $product_menu_parent_ids, array_filter( array( absint( $product_item->ID ?? 0 ), absint( $product_item->db_id ?? 0 ) ) ) );
	}
	$product_menu_parent_ids = array_values( array_unique( $product_menu_parent_ids ) );
	$candidate_was_current = $products && array_intersect( (array) ( $products->classes ?? array() ), array( 'current-menu-item', 'current_page_item', 'current-menu-parent', 'current-menu-ancestor', 'current_page_parent', 'current_page_ancestor' ) );

	if ( $products ) {
		foreach ( $items as $item ) {
			if ( ! is_object( $item ) || ! in_array( absint( $item->menu_item_parent ?? 0 ), $product_menu_parent_ids, true ) ) {
				continue;
			}
			$product_menu_items[] = $item;
			$product_menu_descendant_ids[] = absint( $item->ID ?? 0 );
			$product_menu_descendant_ids[] = absint( $item->db_id ?? 0 );
		}
	}
	$product_menu_parent_ids = array_values( array_unique( array_merge( $product_menu_parent_ids, array_filter( $product_menu_descendant_ids ) ) ) );
	$GLOBALS['sarafatto_primary_products_menu_items'] = $product_menu_items;

	foreach ( $items as $index => $item ) {
		if ( ! is_object( $item ) ) {
			$prepared[] = $item;
			continue;
		}
		if ( in_array( absint( $item->menu_item_parent ?? 0 ), $product_menu_parent_ids, true ) ) {
			continue;
		}

		$item_title = strtolower( trim( wp_strip_all_tags( (string) ( $item->title ?? '' ) ) ) );
		$is_products = ( isset( $item->object ) && 'sarafatto_prodotto' === $item->object )
			|| ( isset( $item->url ) && $archive_key === sarafatto_normalize_menu_url( $item->url ) )
			|| $products_label === $item_title;
		$is_news = null !== $news_index && $index === $news_index && ! $is_products;

		if ( $index !== $candidate_index && ( $is_news || $is_products ) ) {
			continue;
		}
		if ( $index === $candidate_index ) {
			$item->object    = 'sarafatto_prodotto';
			$item->object_id = 0;
			$item->type      = 'post_type_archive';
			$item->url       = $archive_url;
			$item->title     = sarafatto_theme_label( 'Prodotti', 'Products' );
			$products        = $item;
		}
		$prepared[] = $item;
	}

	$needs_insert = null === $candidate_index;
	if ( $needs_insert ) {
		$products = sarafatto_create_products_menu_item( $archive_url, null !== $news_index ? $news_index + 1 : 1 );
	}

	$products->classes = array_values(
		array_unique(
			array_merge(
				array_diff( (array) ( $products->classes ?? array() ), array( 'current-menu-item', 'current_page_item', 'current-menu-parent', 'current-menu-ancestor' ) ),
				array( 'menu-item', 'menu-item-type-post_type_archive', 'menu-item-object-sarafatto_prodotto', 'menu-item-has-children', 'sarafatto-menu-products' )
			)
		)
	);
	$is_products_context = ( function_exists( 'is_post_type_archive' ) && is_post_type_archive( 'sarafatto_prodotto' ) )
		|| ( function_exists( 'is_singular' ) && is_singular( 'sarafatto_prodotto' ) )
		|| ( function_exists( 'is_tax' ) && is_tax( array( 'sarafatto_categoria', 'sarafatto_occasione', 'sarafatto_idea_regalo' ) ) )
		|| ! empty( $candidate_was_current );
	foreach ( $product_menu_items as $product_menu_item ) {
		if ( array_intersect( (array) ( $product_menu_item->classes ?? array() ), array( 'current-menu-item', 'current_page_item', 'current-menu-parent', 'current-menu-ancestor', 'current_page_parent', 'current_page_ancestor' ) ) ) {
			$is_products_context = true;
			break;
		}
	}
	$products->classes = array_values( array_diff( $products->classes, array( 'is-current-section' ) ) );
	if ( $is_products_context ) {
		$products->classes[] = 'is-current-section';
	}
	$products->menu_item_parent = 0;
	$products->url              = $archive_url;

	if ( $needs_insert ) {
		array_splice( $prepared, min( $insert_at, count( $prepared ) ), 0, array( $products ) );
	}
	return array_values( $prepared );
}
add_filter( 'wp_nav_menu_objects', 'sarafatto_prepare_primary_navigation', 20, 2 );

/** Find an image attachment from its Media Library filename. */
function sarafatto_get_menu_promo_image_id( $filename, $global = false ) {
	static $cache = array();
	$filename = sanitize_file_name( (string) $filename );
	if ( '' === $filename ) {
		return 0;
	}
	$cache_key = $filename . ( $global ? '|global' : '|current-language' );
	if ( array_key_exists( $cache_key, $cache ) ) {
		return $cache[ $cache_key ];
	}

	$query_args = array(
			'post_type'      => 'attachment',
			'post_status'    => 'inherit',
			'posts_per_page' => 20,
			'fields'         => 'ids',
			'meta_query'     => array(
				array(
					'key'     => '_wp_attached_file',
					'value'   => $filename,
					'compare' => 'LIKE',
				),
			),
		);
	if ( $global ) {
		// An empty Polylang language query returns attachments from every language.
		$query_args['lang'] = '';
	}
	$attachments = get_posts( $query_args );

	$cache[ $cache_key ] = 0;
	foreach ( $attachments as $attachment_id ) {
		$attached_file = get_post_meta( $attachment_id, '_wp_attached_file', true );
		if ( basename( (string) $attached_file ) === $filename && wp_attachment_is_image( $attachment_id ) ) {
			$cache[ $cache_key ] = absint( $attachment_id );
			break;
		}
	}

	return $cache[ $cache_key ];
}

/** Return the single active menu promotion shared by desktop and mobile. */
function sarafatto_get_menu_promo_banner() {
	static $promo = null;
	if ( null !== $promo ) {
		return $promo;
	}

	$active_occasions = function_exists( 'sarafatto_get_active_occasions' ) ? sarafatto_get_active_occasions() : array();
	$active_occasions = is_array( $active_occasions ) ? $active_occasions : array();
	usort(
		$active_occasions,
		static function ( $left, $right ) {
			$left_start  = $left instanceof WP_Term ? (string) get_term_meta( $left->term_id, 'sarafatto_occasion_start_date', true ) : '';
			$right_start = $right instanceof WP_Term ? (string) get_term_meta( $right->term_id, 'sarafatto_occasion_start_date', true ) : '';
			return strcmp( $right_start, $left_start );
		}
	);

	foreach ( $active_occasions as $occasion ) {
		if ( ! $occasion instanceof WP_Term ) {
			continue;
		}

		$image_id = absint( get_term_meta( $occasion->term_id, 'sarafatto_occasion_image', true ) );
		if ( ! $image_id || ! wp_attachment_is_image( $image_id ) ) {
			$occasion_slugs = array( sanitize_title( $occasion->slug ) );
			if ( function_exists( 'pll_get_term' ) ) {
				$italian_term_id = absint( pll_get_term( $occasion->term_id, 'it' ) );
				$italian_term    = $italian_term_id ? get_term( $italian_term_id, 'sarafatto_occasione' ) : null;
				if ( $italian_term instanceof WP_Term ) {
					$occasion_slugs[] = sanitize_title( $italian_term->slug );
				}
			}
			$occasion_slugs = array_unique( array_filter( $occasion_slugs ) );
			foreach ( $occasion_slugs as $occasion_slug ) {
				foreach ( array( '_occasioni_banner.png', '_occasione_banner.png' ) as $filename_suffix ) {
					$image_id = sarafatto_get_menu_promo_image_id( $occasion_slug . $filename_suffix );
					if ( $image_id ) {
						break 2;
					}
				}
			}
		}
		if ( ! $image_id ) {
			continue;
		}

		$occasion_url = get_term_link( $occasion );
		if ( is_wp_error( $occasion_url ) ) {
			continue;
		}

		$editorial_title = get_term_meta( $occasion->term_id, 'sarafatto_occasion_title', true );
		$intro           = get_term_meta( $occasion->term_id, 'sarafatto_occasion_intro', true );
		$name            = wp_strip_all_tags( (string) $occasion->name );
		$promo = array(
			'type'      => 'occasion',
			'image_id'  => $image_id,
			'image_url' => wp_get_attachment_image_url( $image_id, 'full' ) ?: '',
			'eyebrow'   => $name,
			'title'     => is_scalar( $editorial_title ) && '' !== trim( (string) $editorial_title ) ? wp_strip_all_tags( (string) $editorial_title ) : $name,
			'text'      => is_scalar( $intro ) ? wp_strip_all_tags( (string) $intro ) : '',
			'label'     => sprintf( sarafatto_theme_label( 'Scopri %s', 'Explore %s' ), $name ),
			'url'       => esc_url_raw( $occasion_url ),
			'term_id'   => absint( $occasion->term_id ),
		);
		return $promo;
	}

	$shipping_page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( 'spedizioni' ) : null;
	$shipping_url  = $shipping_page instanceof WP_Post ? get_permalink( $shipping_page->ID ) : '';
	$image_id      = sarafatto_get_menu_promo_image_id( 'spedizioni_banner_menu.png', true );
	$promo = array(
		'type'      => 'shipping',
		'image_id'  => $image_id,
		'image_url' => $image_id ? ( wp_get_attachment_image_url( $image_id, 'full' ) ?: '' ) : '',
		'eyebrow'   => sarafatto_theme_label( 'ANCHE SE SEI LONTANO', 'EVEN IF YOU ARE FAR AWAY' ),
		'title'     => sarafatto_theme_label( "Peschici è lontana?\nIl corriere un po’ meno.", "Is Peschici far away?\nThe courier, a little less so." ),
		'text'      => sarafatto_theme_label( 'Spedizioni in Italia e in Europa.', 'Shipping across Italy and Europe.' ),
		'label'     => sarafatto_theme_label( 'Come funziona', 'How it works' ),
		'url'       => $shipping_url ? esc_url_raw( $shipping_url ) : '',
		'term_id'   => 0,
	);
	return $promo;
}

/** Build product panel content from translated categories and current menu items. */
function sarafatto_get_products_menu_data() {
	static $data_cache = null;
	if ( null !== $data_cache ) {
		return $data_cache;
	}
	$archive_url = sarafatto_get_products_archive_url();
	$archive_key = sarafatto_normalize_menu_url( $archive_url );
	$products_label = strtolower( trim( wp_strip_all_tags( sarafatto_theme_label( 'Prodotti', 'Products' ) ) ) );
	$news_url    = function_exists( 'sarafatto_get_home_news_url' ) ? sarafatto_get_home_news_url() : '';
	$category_args = array(
		'taxonomy'   => 'sarafatto_categoria',
		'hide_empty' => false,
		'orderby'    => 'term_order',
		'order'      => 'ASC',
		'number'     => 0,
	);
	if ( function_exists( 'sarafatto_add_language_to_query_args' ) ) {
		$category_args = sarafatto_add_language_to_query_args( $category_args );
	}

	$categories = get_terms( $category_args );
	if ( is_wp_error( $categories ) || ! is_array( $categories ) ) {
		$categories = array();
	}
	$occasion_args = array(
		'taxonomy'   => 'sarafatto_occasione',
		'hide_empty' => false,
		'fields'     => 'all',
	);
	if ( function_exists( 'sarafatto_add_language_to_query_args' ) ) {
		$occasion_args = sarafatto_add_language_to_query_args( $occasion_args );
	}
	$all_occasion_terms = get_terms( $occasion_args );
	if ( is_wp_error( $all_occasion_terms ) || ! is_array( $all_occasion_terms ) ) {
		$all_occasion_terms = array();
	}

	$current_request = isset( $_SERVER['REQUEST_URI'] ) ? wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
	$current_url = $current_request ? home_url( $current_request ) : '';
	$current_key = sarafatto_normalize_menu_url( $current_url );
	$is_current_url = static function ( $url ) use ( $current_key ) {
		return '' !== $current_key && $current_key === sarafatto_normalize_menu_url( $url );
	};
	$news_key = sarafatto_normalize_menu_url( $news_url );
	$news_link = null;
	$menu_links = array();
	$represented_urls = array();
	$occasion_urls = array();
	foreach ( $all_occasion_terms as $occasion_term ) {
		if ( ! $occasion_term instanceof WP_Term ) {
			continue;
		}
		$occasion_term_url = get_term_link( $occasion_term );
		if ( ! is_wp_error( $occasion_term_url ) ) {
			$occasion_urls[] = sarafatto_normalize_menu_url( $occasion_term_url );
		}
	}

	foreach ( (array) ( $GLOBALS['sarafatto_primary_products_menu_items'] ?? array() ) as $menu_item ) {
		if ( ! is_object( $menu_item ) || empty( $menu_item->url ) || '#' === $menu_item->url ) {
			continue;
		}
		$url_key = sarafatto_normalize_menu_url( $menu_item->url );
		$item_title = strtolower( trim( wp_strip_all_tags( (string) ( $menu_item->title ?? '' ) ) ) );
		if ( $products_label === $item_title || ( '' !== $archive_key && $archive_key === $url_key ) ) {
			continue;
		}
		if ( in_array( $url_key, $occasion_urls, true ) ) {
			continue;
		}
		$link = array(
			'title'  => wp_strip_all_tags( (string) $menu_item->title ),
			'url'    => esc_url_raw( $menu_item->url ),
			'active' => (bool) array_intersect( (array) ( $menu_item->classes ?? array() ), array( 'current-menu-item', 'current_page_item', 'current-menu-parent', 'current-menu-ancestor', 'current_page_parent', 'current_page_ancestor' ) ) || $is_current_url( $menu_item->url ),
		);
		if ( '' !== $news_key && $news_key === $url_key ) {
			$news_link = $link;
			$represented_urls[] = $url_key;
			continue;
		}
		if ( in_array( $url_key, $represented_urls, true ) ) {
			continue;
		}
		$menu_links[] = $link;
		$represented_urls[] = $url_key;
	}
	if ( ! $news_link && $news_url ) {
		$news_link = array(
			'title'  => sarafatto_theme_label( 'Novità', 'New arrivals' ),
			'url'    => $news_url,
			'active' => $is_current_url( $news_url ),
		);
		$represented_urls[] = $news_key;
	}

	$category_links = array();
	foreach ( $categories as $category ) {
		if ( ! $category instanceof WP_Term ) {
			continue;
		}
		$term_url = get_term_link( $category );
		if ( is_wp_error( $term_url ) ) {
			continue;
		}
		$category_links[] = array(
			'term' => $category,
			'url'  => $term_url,
		);
		$term_key = sarafatto_normalize_menu_url( $term_url );
		if ( ! in_array( $term_key, $represented_urls, true ) ) {
			$is_current_category = function_exists( 'is_tax' ) && is_tax( 'sarafatto_categoria', $category->slug );
			if ( ! $is_current_category && function_exists( 'is_tax' ) && is_tax( 'sarafatto_categoria' ) ) {
				$current_term = get_queried_object();
				$is_current_category = $current_term instanceof WP_Term && term_is_ancestor_of( $category->term_id, $current_term->term_id, 'sarafatto_categoria' );
			}
			$menu_links[] = array(
				'title'  => $category->name,
				'url'    => $term_url,
				'active' => $is_current_category,
			);
			$represented_urls[] = $term_key;
		}
	}

	$data_cache = array(
		'archive_url'   => $archive_url,
		'archive_active'=> function_exists( 'is_post_type_archive' ) && is_post_type_archive( 'sarafatto_prodotto' ),
		'news_link'     => $news_link,
		'menu_links'    => $menu_links,
		'categories'    => $category_links,
		'promo'         => sarafatto_get_menu_promo_banner(),
		'english'       => function_exists( 'sarafatto_get_current_language' ) && 0 === strpos( sarafatto_get_current_language(), 'en' ),
	);
	return $data_cache;
}

/** Append the shared promotion after the first-level links for the mobile drawer. */
function sarafatto_append_mobile_menu_promo( $items, $args ) {
	if ( empty( $args->theme_location ) || 'primary' !== $args->theme_location || ! is_string( $items ) ) {
		return $items;
	}

	ob_start();
	get_template_part( 'template-parts/components/menu-promo', null, array( 'promo' => sarafatto_get_menu_promo_banner(), 'context' => 'mobile' ) );
	$promo = (string) ob_get_clean();
	if ( '' === trim( $promo ) ) {
		return $items;
	}

	return $items . '<li class="menu-item site-navigation__promo">' . $promo . '</li>';
}
add_filter( 'wp_nav_menu_items', 'sarafatto_append_mobile_menu_promo', 20, 2 );

/** Append the disclosure control and the editorial panel to the Products menu item. */
function sarafatto_render_products_menu_item( $item_output, $item, $depth, $args ) {
	if ( empty( $args->theme_location ) || 'primary' !== $args->theme_location || ! in_array( 'sarafatto-menu-products', (array) ( $item->classes ?? array() ), true ) ) {
		return $item_output;
	}

	$panel_id = 'site-products-menu-' . absint( $item->ID );
	$title    = sarafatto_theme_label( 'Prodotti', 'Products' );
	$item_output = preg_replace( '/<a\b[^>]*>(.*?)<\/a>/s', '<span class="site-navigation__label">$1</span>', $item_output, 1 );
	$button   = sprintf(
		'<button class="site-navigation__submenu-toggle" type="button" aria-haspopup="true" aria-expanded="false" aria-controls="%1$s-desktop %1$s-mobile" aria-label="%2$s"><span class="screen-reader-text">%2$s</span><span class="site-navigation__chevron" aria-hidden="true"></span></button>',
		esc_attr( $panel_id ),
		esc_attr( sprintf( sarafatto_theme_label( 'Apri il menu di %s', 'Open the %s menu' ), $title ) )
	);

	ob_start();
	get_template_part( 'template-parts/components/products-menu', null, array( 'panel_id' => $panel_id ) );
	$panel = (string) ob_get_clean();
	return $item_output . $button . $panel;
}
add_filter( 'walker_nav_menu_start_el', 'sarafatto_render_products_menu_item', 20, 4 );

/** Add accessible disclosure controls to regular WordPress menu items with children. */
function sarafatto_add_submenu_disclosure( $item_output, $item, $depth, $args ) {
	if ( 0 !== (int) $depth || empty( $args->theme_location ) || 'primary' !== $args->theme_location || in_array( 'sarafatto-menu-products', (array) ( $item->classes ?? array() ), true ) || ! in_array( 'menu-item-has-children', (array) ( $item->classes ?? array() ), true ) ) {
		return $item_output;
	}

	$submenu_id = 'site-submenu-' . absint( $item->ID );
	$title      = wp_strip_all_tags( (string) $item->title );
	$label      = sprintf( sarafatto_theme_label( 'Apri il menu di %s', 'Open the %s menu' ), $title );
	return $item_output . sprintf(
		'<button class="site-navigation__submenu-toggle" type="button" aria-haspopup="true" aria-expanded="false" aria-controls="%1$s" aria-label="%2$s"><span class="screen-reader-text">%2$s</span><span class="site-navigation__chevron" aria-hidden="true"></span></button>',
		esc_attr( $submenu_id ),
		esc_attr( $label )
	);
}
add_filter( 'walker_nav_menu_start_el', 'sarafatto_add_submenu_disclosure', 10, 4 );

/** Use the archive navigation walker for the primary menu. */
function sarafatto_primary_nav_args( $args ) {
	if ( isset( $args['theme_location'] ) && 'primary' === $args['theme_location'] ) {
		$args['walker'] = new Sarafatto_Primary_Nav_Walker();
		$args['fallback_cb'] = false;
	}
	return $args;
}
add_filter( 'wp_nav_menu_args', 'sarafatto_primary_nav_args' );

/** Wrap ordinary WordPress child lists so mobile can present them as a backable view. */
class Sarafatto_Primary_Nav_Walker extends Walker_Nav_Menu {
	private $submenu_ids = array();
	private $submenu_titles = array();

	public function start_el( &$output, $data_object, $depth = 0, $args = null, $current_object_id = 0 ) {
		$this->submenu_ids[ $depth ]    = 'site-submenu-' . absint( $data_object->ID );
		$this->submenu_titles[ $depth ] = wp_strip_all_tags( (string) $data_object->title );
		parent::start_el( $output, $data_object, $depth, $args, $current_object_id );
	}

	public function start_lvl( &$output, $depth = 0, $args = null ) {
		$indent = str_repeat( "\t", $depth );
		$id     = $this->submenu_ids[ $depth ] ?? '';
		$title  = $this->submenu_titles[ $depth ] ?? '';
		$output .= "\n$indent<div class=\"site-navigation__subview\" id=\"" . esc_attr( $id ) . "\" aria-hidden=\"true\" inert>\n";
		$output .= $indent . "\t<div class=\"site-navigation__subview-header\"><button class=\"site-navigation__back\" type=\"button\" aria-label=\"" . esc_attr( sarafatto_theme_label( 'Indietro', 'Back' ) ) . "\"><span class=\"icon-[mdi--arrow-left]\" aria-hidden=\"true\"></span></button><span class=\"site-navigation__subview-title\">" . esc_html( $title ) . "</span></div>\n";
		$output .= $indent . "\t<ul class=\"site-navigation__sublist\" aria-label=\"" . esc_attr( $title ) . "\">\n";
	}

	public function end_lvl( &$output, $depth = 0, $args = null ) {
		$indent = str_repeat( "\t", $depth );
		$output .= "$indent\t</ul>\n$indent</div>\n";
	}
}
