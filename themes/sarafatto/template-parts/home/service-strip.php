<?php
/** Compact strip of the actual shop services. */
if ( ! defined( 'ABSPATH' ) ) { exit; }

$services = array();
$linked_pages = array(
	'idee_regalo'    => array( 'Idee regalo', 'Gift ideas', 'Trovi idee per occasioni diverse.', 'Find ideas for different occasions.', 'icon-[mdi--gift-outline]' ),
	'personalizzati' => array( 'Personalizzati', 'Personalised', 'Parole e dettagli pensati insieme.', 'Words and details made personal.', 'icon-[mdi--creation-outline]' ),
	'spedizioni'     => array( 'Spedizioni', 'Shipping', 'Spedizioni in Italia e in Europa.', 'Shipping across Italy and Europe.', 'icon-[mdi--truck-outline]' ),
);
foreach ( $linked_pages as $role => $copy ) {
	$page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( $role ) : null;
	$services[] = array( 'title' => sarafatto_theme_label( $copy[0], $copy[1] ), 'text' => sarafatto_theme_label( $copy[2], $copy[3] ), 'icon' => $copy[4], 'url' => $page instanceof WP_Post ? get_permalink( $page->ID ) : '' );
}
$whatsapp_url = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url() : '';
$services[] = array( 'title' => sarafatto_theme_label( 'Scrivimi su WhatsApp', 'Message me on WhatsApp' ), 'text' => sarafatto_theme_label( 'Ti aiuto a scegliere l’idea giusta.', 'I can help you find the right idea.' ), 'icon' => 'icon-[mdi--chat-processing-outline]', 'url' => $whatsapp_url, 'external' => true );
?>
<section class="home-service-strip" aria-label="<?php echo esc_attr( sarafatto_theme_label( 'Servizi SaràFatto', 'SaràFatto services' ) ); ?>">
	<ul class="home-service-strip__list">
		<?php foreach ( $services as $service ) : ?>
			<li class="home-service-strip__item">
				<?php if ( $service['url'] ) : ?><a href="<?php echo esc_url( $service['url'] ); ?>"<?php echo ! empty( $service['external'] ) ? ' target="_blank" rel="noopener noreferrer"' : ''; ?>><?php else : ?><div class="home-service-strip__item-content"><?php endif; ?>
					<span class="home-service-strip__icon <?php echo esc_attr( $service['icon'] ); ?>" aria-hidden="true"></span>
					<span class="home-service-strip__copy"><span class="home-service-strip__title"><?php echo esc_html( $service['title'] ); ?></span><span class="home-service-strip__text"><?php echo esc_html( $service['text'] ); ?></span></span>
				<?php if ( $service['url'] ) : ?></a><?php else : ?></div><?php endif; ?>
			</li>
		<?php endforeach; ?>
	</ul>
</section>
