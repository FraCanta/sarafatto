<?php
/** Editorial mosaic for product worlds; replace the isolated sample labels when the lines are managed in the backend. */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$worlds = array(
	array( 'Saluti da qui', 'Greetings from here' ),
	array( 'Mani sante', 'Magic hands' ),
	array( 'Sorprendimi', 'Surprise me' ),
	array( 'Pochette ricamate', 'Embroidered pouches' ),
	array( 'Kiki borse', 'Kiki bags' ),
);
?>
<section class="home-worlds" aria-labelledby="home-worlds-title">
	<div class="home-container">
		<header class="home-worlds__intro">
			<h2 class="home-section-title" id="home-worlds-title"><?php echo esc_html( sarafatto_theme_label( 'I nostri mondi', 'Our worlds' ) ); ?></h2>
		</header>
		<ul class="home-worlds__grid">
			<?php foreach ( $worlds as $index => $world ) : ?>
				<li class="home-worlds__item home-worlds__item--<?php echo esc_attr( $index + 1 ); ?>">
					<div class="home-worlds__placeholder" aria-hidden="true"></div>
					<h3 class="home-worlds__label"><?php echo esc_html( sarafatto_theme_label( $world[0], $world[1] ) ); ?></h3>
				</li>
			<?php endforeach; ?>
		</ul>
	</div>
</section>
