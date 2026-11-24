<?php
/** Editorial mosaic for product worlds; replace the isolated sample labels when the lines are managed in the backend. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$worlds = array(
	array( 'Saluti da qui', 'Greetings from here', 'home-saluti-da-qui.png' ),
	array( 'Mani sante', 'Magic hands', 'home-mani-sante.png' ),
	array( 'Soorprendimi', 'Surprise me', 'home-sorprendimi.png' ),
	array( 'Pochette ricamate', 'Embroidered pouches', '' ),
	array( 'Kiki borse', 'Kiki bags', 'home-kiki-borse.webp' ),
);
?>
<section class="home-worlds" aria-labelledby="home-worlds-title">
	<div class="home-container">
		<header class="home-worlds__intro">
			<h2 class="home-section-title" id="home-worlds-title"><?php echo esc_html( sarafatto_theme_label( 'Le mie collezioni', 'My collections' ) ); ?></h2>
		</header>
		<ul class="home-worlds__grid">
			<?php foreach ( $worlds as $index => $world ) : ?>
				<li class="home-worlds__item home-worlds__item--<?php echo esc_attr( $index + 1 ); ?><?php echo ! empty( $world[2] ) ? ' home-worlds__item--has-image' : ''; ?>">
					<div class="home-worlds__placeholder" aria-hidden="true"></div>
					<?php if ( ! empty( $world[2] ) ) : ?>
						<img class="home-worlds__image" src="<?php echo esc_url( get_theme_file_uri( 'assets/images/' . $world[2] ) ); ?>" alt="" width="1238" height="1238" loading="lazy" decoding="async" />
					<?php endif; ?>
					<h3 class="home-worlds__label"><?php echo esc_html( sarafatto_theme_label( $world[0], $world[1] ) ); ?></h3>
				</li>
			<?php endforeach; ?>
		</ul>
	</div>
</section>
