<?php
/** Theme supports and menus. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function sarafatto_setup() {
	load_theme_textdomain( 'sarafatto', get_theme_file_path( '/languages' ) );
	add_theme_support( 'title-tag' );
	add_theme_support( 'post-thumbnails' );
	add_theme_support( 'custom-logo', array( 'height' => 160, 'width' => 320, 'flex-height' => true, 'flex-width' => true ) );
	add_theme_support( 'html5', array( 'search-form', 'comment-form', 'comment-list', 'gallery', 'caption', 'style', 'script', 'navigation-widgets' ) );
	add_theme_support( 'align-wide' );
	add_theme_support( 'responsive-embeds' );
	add_theme_support( 'editor-styles' );
	add_editor_style( 'assets/src/css/editor.css' );
	foreach (
		array(
			'sarafatto-primary'   => __( 'SaràFatto · Primario', 'sarafatto' ),
			'sarafatto-accent'    => __( 'SaràFatto · Accento', 'sarafatto' ),
			'sarafatto-secondary' => __( 'SaràFatto · Secondario', 'sarafatto' ),
			'sarafatto-text'      => __( 'SaràFatto · Testuale', 'sarafatto' ),
		) as $style_name => $style_label
	) {
		register_block_style(
			'core/button',
			array(
				'name'  => $style_name,
				'label' => $style_label,
			)
		);
	}
	register_nav_menus(
		array(
			'primary'      => __( 'Menu principale', 'sarafatto' ),
			'footer'       => __( 'Menu footer', 'sarafatto' ),
			'footer-legal' => __( 'Menu legale footer', 'sarafatto' ),
		)
	);
}
add_action( 'after_setup_theme', 'sarafatto_setup' );
