<?php
/** Theme-managed Home Hero, rendered outside the page editor. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Resolve the translated Novità destination for the Home Hero. */
function sarafatto_get_home_news_url() {
	$locations = get_nav_menu_locations();
	$menu_id   = isset( $locations['primary'] ) ? absint( $locations['primary'] ) : 0;
	$items     = $menu_id ? wp_get_nav_menu_items( $menu_id ) : array();
	$items     = is_array( $items ) ? $items : array();
	$label     = function_exists( 'sarafatto_theme_label' )
		? sarafatto_theme_label( 'Novità', 'New arrivals' )
		: ( function_exists( 'pll_current_language' ) && 'en' === pll_current_language( 'slug' ) ? 'New arrivals' : 'Novità' );

	foreach ( $items as $item ) {
		if ( isset( $item->title, $item->url ) && sanitize_title( $item->title ) === sanitize_title( $label ) ) {
			return esc_url_raw( $item->url );
		}
	}

	return home_url( '/novita/' );
}

/** Supply translated copy for the theme-managed Home Hero. */
function sarafatto_home_hero_defaults() {
	return array(
		'eyebrow'        => sarafatto_theme_label( 'Oggetti, accessori, idee.', 'Objects, accessories, ideas.' ),
		'headlineLine1'  => sarafatto_theme_label( 'Non tutto.', 'Not everything.' ),
		'headlineLine2'  => sarafatto_theme_label( 'Solo quello', 'Only what' ),
		'headlineLine3'  => sarafatto_theme_label( 'che ha', 'has' ),
		'headlineAccent' => sarafatto_theme_label( 'qualcosa.', 'something.' ),
		'description'    => sarafatto_theme_label( 'Cose originali, ironiche e di qualità, scelte con un certo gusto (e un pizzico di imprevedibilità).', 'Original, witty, quality finds, chosen with taste (and a little unpredictability).' ),
		'ctaLabel'       => sarafatto_theme_label( 'Scopri le novità', 'Discover what’s new' ),
	);
}

/** Render the fixed Home Hero outside the Gutenberg page content. */
function sarafatto_render_home_hero() {
	$content = sarafatto_home_hero_defaults();
	$desktop = array( get_theme_file_uri( 'assets/images/home-hero-desktop.png' ), 1672, 941 );
	$mobile  = array( get_theme_file_uri( 'assets/images/home-hero-mobile.png' ), 941, 1672 );
	$news_url = sarafatto_get_home_news_url();

	return sprintf(
		'<section class="home-hero" aria-labelledby="home-hero-title"><div class="home-hero__inner"><div class="home-hero__content"><p class="eyebrow home-hero__eyebrow">%1$s</p><h1 id="home-hero-title" class="home-hero__title"><span>%2$s</span> <span>%3$s</span> <span>%4$s <span class="home-hero__underline editorial-underline editorial-underline--01">%5$s</span></span></h1><p class="home-hero__description">%6$s</p><a class="button button--primary button--lg home-hero__button" href="%7$s">%8$s <span class="button__icon icon-[mdi--arrow-top-right]" aria-hidden="true"></span></a></div><figure class="home-hero__visual" aria-hidden="true"><picture><source media="(min-width: 48rem) and (max-width: 63.999rem)" srcset="%12$s" width="%13$d" height="%14$d"><source media="(max-width: 48.875rem)" srcset="%9$s" width="%10$d" height="%11$d"><img class="home-hero__image" src="%12$s" sizes="(min-width: 48rem) and (max-width: 63.999rem) 88vw, (min-width: 48.875rem) 60vw, 90vw" alt="" width="%13$d" height="%14$d" fetchpriority="high" decoding="async"></picture></figure></div></section>',
		wp_kses_post( $content['eyebrow'] ),
		wp_kses_post( $content['headlineLine1'] ),
		wp_kses_post( $content['headlineLine2'] ),
		wp_kses_post( $content['headlineLine3'] ),
		wp_kses_post( $content['headlineAccent'] ),
		wp_kses_post( $content['description'] ),
		esc_url( $news_url ),
		esc_html( wp_strip_all_tags( $content['ctaLabel'] ) ),
		esc_url( $mobile[0] ),
		absint( $mobile[1] ),
		absint( $mobile[2] ),
		esc_url( $desktop[0] ),
		absint( $desktop[1] ),
		absint( $desktop[2] )
	);
}
