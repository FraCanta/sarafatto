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
$footer_logo_ids = get_posts(
	array(
		'post_type'      => 'attachment',
		'post_status'    => 'inherit',
		'posts_per_page' => 1,
		'fields'         => 'ids',
		'meta_query'     => array(
			array(
				'key'     => '_wp_attached_file',
				'value'   => 'logo_positivo_footer.png',
				'compare' => 'LIKE',
			),
		),
	)
);
$footer_logo_id = $footer_logo_ids ? absint( $footer_logo_ids[0] ) : 0;
	$footer_home_url = function_exists( 'sarafatto_get_language_home_url' )
	? sarafatto_get_language_home_url()
	: home_url( '/' );
$socials = array_filter(
	array(
		'Instagram' => array( $get_setting( 'social_instagram' ), 'icon-[mdi--instagram]' ),
		'Facebook'  => array( $get_setting( 'social_facebook' ), 'icon-[mdi--facebook]' ),
		'TikTok'    => array( $get_setting( 'social_tiktok' ), 'icon-[mdi--music-note]' ),
		'Pinterest' => array( $get_setting( 'social_pinterest' ), 'icon-[mdi--pinterest]' ),
	),
	static function ( $social ) { return is_array( $social ) && is_string( $social[0] ) && '' !== trim( $social[0] ); }
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

$explore_items = array();
$products_url = function_exists( 'sarafatto_get_products_archive_url' ) ? sarafatto_get_products_archive_url() : get_post_type_archive_link( 'sarafatto_prodotto' );
if ( $products_url ) {
	$explore_items[] = array( 'label' => sarafatto_theme_label( 'Prodotti', 'Products' ), 'url' => $products_url );
}
foreach (
	array(
		'idee_regalo'    => array( 'Idee regalo', 'Gift ideas' ),
		'personalizzati' => array( 'Personalizzati', 'Personalised' ),
	) as $role => $labels
) {
	$page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( $role ) : null;
	$url  = $page ? get_permalink( $page ) : '';
	if ( $url ) {
		$explore_items[] = array( 'label' => sarafatto_theme_label( $labels[0], $labels[1] ), 'url' => $url );
	}
}

$privacy_url = function_exists( 'get_privacy_policy_url' ) ? get_privacy_policy_url() : '';
$cookie_url  = '';
$cookie_slugs = array( 'cookie-policy', 'politica-cookie', 'informativa-cookie', 'cookies', 'cookie' );
foreach ( $cookie_slugs as $cookie_slug ) {
	$cookie_page = get_page_by_path( $cookie_slug, OBJECT, 'page' );
	if ( $cookie_page instanceof WP_Post && 'publish' === $cookie_page->post_status ) {
		if ( function_exists( 'pll_current_language' ) && function_exists( 'sarafatto_get_translation_id' ) ) {
			$translated_cookie_id = sarafatto_get_translation_id( $cookie_page->ID, 'post', sarafatto_get_current_language() );
			$cookie_page = $translated_cookie_id ? get_post( $translated_cookie_id ) : null;
		}
		if ( $cookie_page instanceof WP_Post && 'publish' === $cookie_page->post_status ) {
			$cookie_url = get_permalink( $cookie_page );
			break;
		}
	}
}
?>
<footer class="site-footer">
	<div class="container">
		<div class="site-footer__main">
			<div class="site-footer__brand">
				<?php if ( $footer_logo_id ) : ?>
					<a class="custom-logo-link" href="<?php echo esc_url( $footer_home_url ); ?>" rel="home" aria-label="<?php echo esc_attr( get_bloginfo( 'name' ) ); ?>">
						<?php echo wp_get_attachment_image( $footer_logo_id, 'full', false, array( 'class' => 'custom-logo', 'alt' => get_bloginfo( 'name' ) ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
					</a>
				<?php elseif ( has_custom_logo() ) : ?>
					<a class="custom-logo-link" href="<?php echo esc_url( function_exists( 'sarafatto_get_language_home_url' ) ? sarafatto_get_language_home_url() : home_url( '/' ) ); ?>" rel="home" aria-label="<?php echo esc_attr( get_bloginfo( 'name' ) ); ?>">
						<?php echo wp_get_attachment_image( get_theme_mod( 'custom_logo' ), 'full', false, array( 'class' => 'custom-logo', 'alt' => get_bloginfo( 'name' ) ) ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
					</a>
				<?php else : ?>
					<a class="site-footer__brand-name" href="<?php echo esc_url( $footer_home_url ); ?>"><?php echo esc_html( get_bloginfo( 'name' ) ); ?></a>
				<?php endif; ?>
			</div>

			<?php if ( $explore_items ) : ?>
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
					</ul>
					<?php if ( $socials ) : ?>
						<ul class="site-footer__socials" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Seguimi sui social', 'Follow me on social media' ) ); ?>">
							<?php foreach ( $socials as $name => $social ) : ?>
								<li><a href="<?php echo esc_url( $social[0] ); ?>" target="_blank" rel="noopener noreferrer" aria-label="<?php echo esc_attr( sprintf( sarafatto_theme_label( '%s di SaràFatto', 'SaràFatto on %s' ), $name ) ); ?>"><span class="site-footer__social-icon <?php echo esc_attr( $social[1] ); ?>" aria-hidden="true"></span><span class="screen-reader-text"><?php echo esc_html( $name ); ?> (<?php echo esc_html( sarafatto_theme_label( 'si apre in una nuova scheda', 'opens in a new tab' ) ); ?>)</span></a></li>
							<?php endforeach; ?>
						</ul>
					<?php endif; ?>
				</section>
			<?php endif; ?>
		</div>

		<div class="site-footer__bottom">
			<?php if ( $privacy_url || $cookie_url ) : ?>
				<nav class="site-footer__legal" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Informazioni legali', 'Legal information' ) ); ?>">
					<ul class="site-footer__list site-footer__legal-list">
						<?php if ( $privacy_url ) : ?><li><a href="<?php echo esc_url( $privacy_url ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Privacy Policy', 'Privacy Policy' ) ); ?></a></li><?php endif; ?>
						<?php if ( $cookie_url ) : ?><li><a href="<?php echo esc_url( $cookie_url ); ?>"><?php echo esc_html( sarafatto_theme_label( 'Cookie Policy', 'Cookie Policy' ) ); ?></a></li><?php endif; ?>
					</ul>
				</nav>
			<?php endif; ?>
			<p class="site-footer__copyright">&copy; <?php echo esc_html( wp_date( 'Y' ) ); ?> <?php echo esc_html( get_bloginfo( 'name' ) ); ?></p>
		</div>
	</div>
</footer>
<?php wp_footer(); ?>
</body>
</html>
