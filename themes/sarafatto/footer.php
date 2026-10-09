<?php
/** Fixed editorial footer with dynamic WordPress and Saràfatto settings. */
if ( ! defined( 'ABSPATH' ) ) { exit; }

$get_setting = static function ( $key ) {
	return function_exists( 'sarafatto_get_setting' ) ? sarafatto_get_setting( $key, '' ) : '';
};
$address_value = $get_setting( 'indirizzo' );
$address = is_scalar( $address_value ) ? trim( (string) $address_value ) : '';
$email = sanitize_email( $get_setting( 'email' ) );
$maps_url = esc_url( $get_setting( 'google_maps_url' ) );
$whatsapp_url = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url() : '';
$socials = array_filter(
	array(
		'Instagram' => $get_setting( 'social_instagram' ),
		'Facebook'  => $get_setting( 'social_facebook' ),
		'TikTok'    => $get_setting( 'social_tiktok' ),
		'Pinterest' => $get_setting( 'social_pinterest' ),
	),
	static function ( $url ) { return is_string( $url ) && '' !== trim( $url ); }
);

$info_pages = array();
if ( function_exists( 'sarafatto_get_linked_page' ) ) {
	foreach ( array( 'spedizioni' => array( 'Spedizioni', 'Shipping' ), 'contatti' => array( 'Contatti', 'Contact' ) ) as $role => $labels ) {
		$page = sarafatto_get_linked_page( $role );
		if ( $page instanceof WP_Post ) {
			$url = get_permalink( $page );
			if ( $url ) { $info_pages[] = array( 'label' => sarafatto_theme_label( $labels[0], $labels[1] ), 'url' => $url ); }
		}
	}
}

$locations = get_nav_menu_locations();
$explore_items = array();
$primary_menu_id = isset( $locations['primary'] ) ? absint( $locations['primary'] ) : 0;
$primary_menu_items = $primary_menu_id ? wp_get_nav_menu_items( $primary_menu_id ) : array();
$primary_menu_items = is_array( $primary_menu_items ) ? $primary_menu_items : array();
$explore_targets = array(
	'novita'         => array( 'Novità', 'New arrivals', '' ),
	'idee_regalo'    => array( 'Idee regalo', 'Gift ideas', 'idee_regalo' ),
	'personalizzati' => array( 'Personalizzati', 'Personalised', 'personalizzati' ),
	'negozio'        => array( 'Il negozio', 'Shop', 'negozio' ),
);
foreach ( $explore_targets as $labels ) {
	$label = sarafatto_theme_label( $labels[0], $labels[1] );
	$url = '';
	foreach ( $primary_menu_items as $menu_item ) {
		if ( isset( $menu_item->title, $menu_item->url ) && sanitize_title( $menu_item->title ) === sanitize_title( $label ) ) {
			$url = $menu_item->url;
			break;
		}
	}
	if ( ! $url && $labels[2] && function_exists( 'sarafatto_get_linked_page' ) ) {
		$page = sarafatto_get_linked_page( $labels[2] );
		$url = $page ? get_permalink( $page ) : '';
	}
	if ( $url ) { $explore_items[] = array( 'label' => $label, 'url' => $url ); }
}

$privacy_url = '';
$privacy_page_id = absint( get_option( 'wp_page_for_privacy_policy' ) );
if ( $privacy_page_id ) {
	if ( function_exists( 'pll_current_language' ) && function_exists( 'sarafatto_get_translation_id' ) ) {
		$privacy_page_id = sarafatto_get_translation_id( $privacy_page_id, 'post', sarafatto_get_current_language() );
	}
	$privacy_page = $privacy_page_id ? get_post( $privacy_page_id ) : null;
	if ( $privacy_page instanceof WP_Post && 'page' === $privacy_page->post_type && 'publish' === $privacy_page->post_status ) {
		$privacy_url = get_permalink( $privacy_page );
	}
}

$legal_menu_id = isset( $locations['footer-legal'] ) ? absint( $locations['footer-legal'] ) : 0;
$legal_menu_items = $legal_menu_id ? wp_get_nav_menu_items( $legal_menu_id ) : array();
$legal_menu_items = is_array( $legal_menu_items ) ? $legal_menu_items : array();
$privacy_in_menu = false;
if ( $privacy_url ) {
	foreach ( $legal_menu_items as $menu_item ) {
		if ( isset( $menu_item->url ) && untrailingslashit( esc_url_raw( $menu_item->url ) ) === untrailingslashit( esc_url_raw( $privacy_url ) ) ) {
			$privacy_in_menu = true;
			break;
		}
	}
}
?>
<footer class="site-footer">
	<div class="container">
		<section class="site-footer__cta" aria-labelledby="site-footer-cta-title">
			<h2 class="site-footer__cta-title" id="site-footer-cta-title">
				<span><?php echo esc_html( sarafatto_theme_label( 'Hai visto qualcosa', 'Found something' ) ); ?></span>
				<span><?php echo esc_html( sarafatto_theme_label( 'che fa per te?', 'that feels like you?' ) ); ?></span>
			</h2>
			<?php if ( $whatsapp_url ) : ?>
				<div class="site-footer__cta-action">
					<?php get_template_part( 'template-parts/components/button', null, array( 'label' => sarafatto_theme_label( 'Scrivici su WhatsApp', 'Message us on WhatsApp' ), 'href' => $whatsapp_url, 'variant' => 'accent', 'size' => 'md', 'icon' => 'arrow-up-right', 'icon_position' => 'after', 'external' => true, 'class' => 'site-footer__cta-button' ) ); ?>
				</div>
			<?php endif; ?>
		</section>

		<div class="site-footer__main">
			<div class="site-footer__brand">
				<?php if ( has_custom_logo() ) : ?>
					<?php the_custom_logo(); ?>
				<?php else : ?>
					<a class="site-footer__brand-name" href="<?php echo esc_url( home_url( '/' ) ); ?>"><?php echo esc_html( get_bloginfo( 'name' ) ); ?></a>
				<?php endif; ?>
			</div>

			<?php if ( has_nav_menu( 'footer' ) ) : ?>
				<nav class="site-footer__group" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Esplora', 'Explore' ) ); ?>">
					<h2 class="site-footer__heading"><?php echo esc_html( sarafatto_theme_label( 'Esplora', 'Explore' ) ); ?></h2>
					<?php wp_nav_menu( array( 'theme_location' => 'footer', 'container' => false, 'menu_class' => 'site-footer__list', 'fallback_cb' => false ) ); ?>
				</nav>
			<?php elseif ( $explore_items ) : ?>
				<nav class="site-footer__group" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Esplora', 'Explore' ) ); ?>">
					<h2 class="site-footer__heading"><?php echo esc_html( sarafatto_theme_label( 'Esplora', 'Explore' ) ); ?></h2>
					<ul class="site-footer__list">
						<?php foreach ( $explore_items as $item ) : ?>
							<li><a href="<?php echo esc_url( $item['url'] ); ?>"><?php echo esc_html( $item['label'] ); ?></a></li>
						<?php endforeach; ?>
					</ul>
				</nav>
			<?php endif; ?>

			<?php if ( $info_pages ) : ?>
				<nav class="site-footer__group" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Informazioni', 'Information' ) ); ?>">
					<h2 class="site-footer__heading"><?php echo esc_html( sarafatto_theme_label( 'Info', 'Info' ) ); ?></h2>
					<ul class="site-footer__list">
						<?php foreach ( $info_pages as $info_page ) : ?>
							<li><a href="<?php echo esc_url( $info_page['url'] ); ?>"><?php echo esc_html( $info_page['label'] ); ?></a></li>
						<?php endforeach; ?>
					</ul>
				</nav>
			<?php endif; ?>

			<?php if ( $whatsapp_url || $email || $address || $maps_url || $socials ) : ?>
				<section class="site-footer__group" aria-labelledby="site-footer-contacts-title">
					<h2 class="site-footer__heading" id="site-footer-contacts-title"><?php echo esc_html( sarafatto_theme_label( 'Contatti', 'Contact' ) ); ?></h2>
					<ul class="site-footer__list site-footer__contact-list">
						<?php if ( $whatsapp_url ) : ?><li><?php get_template_part( 'template-parts/components/whatsapp-link', null, array( 'label' => 'WhatsApp' ) ); ?></li><?php endif; ?>
						<?php if ( $email ) : ?><li><a href="mailto:<?php echo esc_attr( $email ); ?>"><?php echo esc_html( $email ); ?></a></li><?php endif; ?>
						<?php if ( $address ) : ?><li><address><?php echo nl2br( esc_html( $address ) ); ?><?php if ( $maps_url ) : ?> <a href="<?php echo esc_url( $maps_url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( sarafatto_theme_label( 'Apri in Maps', 'Open in Maps' ) ); ?><span class="screen-reader-text"> (<?php echo esc_html( sarafatto_theme_label( 'si apre in una nuova scheda', 'opens in a new tab' ) ); ?>)</span></a><?php endif; ?></address></li><?php endif; ?>
						<?php foreach ( $socials as $name => $url ) : ?>
							<li><a href="<?php echo esc_url( $url ); ?>" target="_blank" rel="noopener noreferrer"><?php echo esc_html( $name ); ?><span class="screen-reader-text"> (<?php echo esc_html( sarafatto_theme_label( 'si apre in una nuova scheda', 'opens in a new tab' ) ); ?>)</span></a></li>
						<?php endforeach; ?>
					</ul>
				</section>
			<?php endif; ?>
		</div>

		<div class="site-footer__bottom">
			<?php if ( ( $privacy_url && ! $privacy_in_menu ) || ( has_nav_menu( 'footer-legal' ) && $legal_menu_items ) ) : ?>
				<nav class="site-footer__legal" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Informazioni legali', 'Legal information' ) ); ?>">
					<?php if ( $privacy_url && ! $privacy_in_menu ) : ?>
						<ul class="site-footer__list site-footer__legal-list"><li><a href="<?php echo esc_url( $privacy_url ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Privacy Policy', 'Privacy Policy' ) ); ?></a></li></ul>
					<?php endif; ?>
					<?php if ( has_nav_menu( 'footer-legal' ) && $legal_menu_items ) : ?>
						<?php wp_nav_menu( array( 'theme_location' => 'footer-legal', 'container' => false, 'menu_class' => 'site-footer__list site-footer__legal-list', 'fallback_cb' => false ) ); ?>
					<?php endif; ?>
				</nav>
			<?php endif; ?>
			<p class="site-footer__copyright">&copy; <?php echo esc_html( wp_date( 'Y' ) ); ?> <?php echo esc_html( get_bloginfo( 'name' ) ); ?></p>
		</div>
	</div>
</footer>
<?php wp_footer(); ?>
</body>
</html>
