<?php
/** Selettore IT / EN personalizzato; Polylang fornisce solo le URL. */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

if ( ! function_exists( 'sarafatto_get_language_switcher_items' ) ) {
	return;
}

$languages = sarafatto_get_language_switcher_items();
if ( empty( $languages ) ) {
	return;
}
$switcher_label = function_exists( 'sarafatto_translate_dynamic_string' ) ? sarafatto_translate_dynamic_string( 'Lingua' ) : 'Lingua';
$unavailable_label = function_exists( 'sarafatto_translate_dynamic_string' ) ? sarafatto_translate_dynamic_string( 'traduzione non disponibile' ) : 'traduzione non disponibile';
$front_page_id = function_exists( 'PLL' ) && isset( PLL()->curlang->page_on_front )
	? absint( PLL()->curlang->page_on_front )
	: absint( get_option( 'page_on_front' ) );
$is_front_page_context = ( function_exists( 'is_front_page' ) && is_front_page() ) || ( $front_page_id && absint( get_queried_object_id() ) === $front_page_id );
?>
<nav class="language-switcher" aria-label="<?php echo esc_attr( $switcher_label ); ?>">
	<ul class="language-switcher__list">
		<?php foreach ( $languages as $language ) : ?>
			<li class="language-switcher__item">
				<?php if ( $language['current'] ) : ?>
					<span class="language-switcher__current" lang="<?php echo esc_attr( $language['slug'] ); ?>" aria-current="page"><?php echo esc_html( $language['label'] ); ?></span>
				<?php elseif ( $is_front_page_context && function_exists( 'sarafatto_get_language_home_url' ) ) : ?>
					<a class="language-switcher__link" href="<?php echo esc_url( sarafatto_get_language_home_url( $language['slug'] ) ); ?>" lang="<?php echo esc_attr( $language['slug'] ); ?>" hreflang="<?php echo esc_attr( $language['slug'] ); ?>"><?php echo esc_html( $language['label'] ); ?></a>
				<?php elseif ( $language['url'] ) : ?>
					<a class="language-switcher__link" href="<?php echo esc_url( $language['url'] ); ?>" lang="<?php echo esc_attr( $language['slug'] ); ?>" hreflang="<?php echo esc_attr( $language['slug'] ); ?>"><?php echo esc_html( $language['label'] ); ?></a>
				<?php else : ?>
					<span class="language-switcher__unavailable" lang="<?php echo esc_attr( $language['slug'] ); ?>"><?php echo esc_html( $language['label'] ); ?><span class="screen-reader-text"> — <?php echo esc_html( $unavailable_label ); ?></span></span>
				<?php endif; ?>
			</li>
		<?php endforeach; ?>
	</ul>
</nav>
