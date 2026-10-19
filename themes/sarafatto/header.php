<?php
/** Site header and responsive primary navigation. */
if ( ! defined( 'ABSPATH' ) ) { exit; }
$header_home_url = function_exists( 'sarafatto_get_language_home_url' )
	? sarafatto_get_language_home_url()
	: home_url( '/' );
?><!doctype html>
<html <?php language_attributes(); ?>>
<head>
	<meta charset="<?php bloginfo( 'charset' ); ?>">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); sarafatto_skip_link(); ?>
<header class="site-header">
	<div class="container site-header__inner">
		<?php if ( has_custom_logo() ) : ?>
			<a class="custom-logo-link" href="<?php echo esc_url( $header_home_url ); ?>" rel="home" aria-label="<?php echo esc_attr( get_bloginfo( 'name' ) ); ?>">
				<?php echo wp_get_attachment_image( get_theme_mod( 'custom_logo' ), 'full', false, array( 'class' => 'custom-logo', 'alt' => get_bloginfo( 'name' ) ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
			</a>
		<?php else : ?>
			<a class="site-title" href="<?php echo esc_url( $header_home_url ); ?>"><?php echo esc_html( get_bloginfo( 'name' ) ); ?></a>
		<?php endif; ?>

		<button class="site-header__toggle" type="button" aria-expanded="false" aria-controls="site-navigation-panel" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Apri il menu', 'Open menu' ) ); ?>" data-open-label="<?php echo esc_attr( sarafatto_theme_label( 'Apri il menu', 'Open menu' ) ); ?>" data-close-label="<?php echo esc_attr( sarafatto_theme_label( 'Chiudi il menu', 'Close menu' ) ); ?>">
			<span class="site-header__toggle-icon" aria-hidden="true"></span>
		</button>

		<div class="site-header__panel" id="site-navigation-panel">
			<h2 class="screen-reader-text" id="site-navigation-title"><?php echo esc_html( sarafatto_theme_label( 'Navigazione principale', 'Main navigation' ) ); ?></h2>
			<?php if ( has_nav_menu( 'primary' ) ) : ?>
				<nav class="site-navigation" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Menu principale', 'Main menu' ) ); ?>">
					<?php wp_nav_menu( array( 'theme_location' => 'primary', 'container' => false, 'menu_class' => 'site-navigation__list' ) ); ?>
				</nav>
			<?php endif; ?>
			<?php get_template_part( 'template-parts/components/language-switcher' ); ?>
		</div>
		<div class="site-header__actions">
			<?php
			$header_whatsapp_url = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url() : '';
			if ( $header_whatsapp_url ) {
				get_template_part(
					'template-parts/components/button',
					null,
					array(
						'label'            => sarafatto_theme_label( 'Scrivimi', 'Message me' ),
						'href'             => $header_whatsapp_url,
						'variant'          => 'primary',
						'size'             => 'sm',
						'icon'             => 'whatsapp',
						'external'         => true,
						'mobile_icon_only' => true,
						'class'            => 'site-header__whatsapp',
					)
				);
			}
			?>
			<?php get_template_part( 'template-parts/components/language-switcher' ); ?>
		</div>
	</div>
</header>
