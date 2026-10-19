<?php
/** Home shipping banner: an editorial invitation to ask Sara about delivery. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$image_url = get_theme_file_uri( 'assets/images/home-shipping-banner.webp' );
$english  = function_exists( 'sarafatto_get_current_language' ) && 0 === strpos( sarafatto_get_current_language(), 'en' );
$alt      = sarafatto_theme_label( 'Primo piano di uno sguardo con un biglietto giallo: “Ti piace? Te lo mando.”', 'Close-up of a playful eye beside a yellow note reading “Ti piace? Te lo mando.”' );

$message = $english
	? 'Hi! I saw the shipping banner and would like to ask about availability, price, and shipping.'
	: 'Ciao! Ho visto il banner e vorrei sapere disponibilità, prezzo e spedizione.';
$whatsapp_url = function_exists( 'sarafatto_get_whatsapp_url' ) ? sarafatto_get_whatsapp_url( $message ) : '';
$shipping_page = function_exists( 'sarafatto_get_linked_page' ) ? sarafatto_get_linked_page( 'spedizioni' ) : null;
$shipping_url  = $shipping_page instanceof WP_Post ? get_permalink( $shipping_page->ID ) : '';

?>
<section class="home-shipping-banner" aria-labelledby="home-shipping-banner-title">
	<figure class="home-shipping-banner__media">
		<img class="home-shipping-banner__image" src="<?php echo esc_url( $image_url ); ?>" alt="<?php echo esc_attr( $alt ); ?>" width="1448" height="1086" sizes="(max-width: 63.999rem) 100vw, 57vw" loading="lazy" decoding="async">
	</figure>
	<div class="home-shipping-banner__content">
		<p class="home-shipping-banner__eyebrow"><?php echo esc_html( sarafatto_theme_label( 'Anche se sei lontano', 'Even if you are far away' ) ); ?></p>
		<h2 class="home-shipping-banner__title" id="home-shipping-banner-title">
			<span><?php echo esc_html( sarafatto_theme_label( 'Peschici', 'Peschici' ) ); ?></span>
			<span><?php echo esc_html( sarafatto_theme_label( 'è lontana?', 'is far away?' ) ); ?></span>
			<span><?php echo esc_html( sarafatto_theme_label( 'Il corriere', 'The courier' ) ); ?></span>
			<span><?php echo esc_html( sarafatto_theme_label( 'un po’ meno.', 'a little less so.' ) ); ?></span>
		</h2>
		<p class="home-shipping-banner__copy"><?php echo esc_html( sarafatto_theme_label( 'Se qualcosa ti ha fatto fermare, scrivimi.', 'If something caught your eye, message me.' ) ); ?><br><?php echo esc_html( sarafatto_theme_label( 'Ti dico disponibilità, prezzo e spedizione.', 'I’ll tell you about availability, price, and shipping.' ) ); ?></p>
		<div class="home-shipping-banner__actions">
			<?php if ( $whatsapp_url ) : ?>
				<?php
				get_template_part(
					'template-parts/components/button',
					null,
					array(
						'label'    => sarafatto_theme_label( 'Chiedi su WhatsApp', 'Ask on WhatsApp' ),
						'href'     => $whatsapp_url,
						'variant'  => 'primary',
						'size'     => 'lg',
						'icon'     => 'whatsapp',
						'external' => true,
						'class'    => 'home-shipping-banner__button',
					)
				);
				?>
			<?php endif; ?>
			<?php if ( $shipping_url ) : ?>
				<?php
				get_template_part(
					'template-parts/components/button',
					null,
					array(
						'label'         => sarafatto_theme_label( 'Come funziona', 'How it works' ),
						'href'          => $shipping_url,
						'variant'       => 'secondary',
						'size'          => 'lg',
						'icon'          => 'arrow-up-right',
						'icon_position' => 'after',
						'class'         => 'home-shipping-banner__button home-shipping-banner__button--shipping',
					)
				);
				?>
			<?php endif; ?>
		</div>
	</div>
</section>
