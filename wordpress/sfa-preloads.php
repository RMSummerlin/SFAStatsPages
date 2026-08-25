<?php
/**
 * Sharp Football Analysis: server-side preload tables.
 *
 * Renders each tool's crawlable stat table into the page HTML so search engines
 * and no-JavaScript visitors see real data. The interactive tool hides it once
 * it has painted; if the tool's data fetch fails, the table stays visible.
 *
 *   [sharp_football_personnel]   personnel grouping frequency
 *   [sharp_football_pace]        offensive pace
 *
 * Paste this file into Code Snippets as a PHP (Functions) snippet, scope "Run
 * everywhere", omitting the opening PHP tag on line 1. Code Snippets supplies it.
 *
 * Structure note: no top-level `return`, no `define()`, no closures. Code
 * Snippets evaluates snippet bodies, and all three behave differently there
 * than in a normal include. This mirrors the shape of the injury report
 * snippet, which has been running in production.
 */

/**
 * All configuration lives here. A function rather than constants so the snippet
 * body is safe to evaluate more than once.
 */
function sfa_preload_config() {
	return array(
		'url'       => 'https://rmsummerlin.github.io/SFAStatsPages/data/preloads.json',
		'timezone'  => 'America/New_York',
		'day'       => 'tuesday',
		'time'      => '23:00',
		'retry'     => 2 * MINUTE_IN_SECONDS,
		'lock_ttl'  => 30,
		'option'    => 'sfa_preloads_last_good',
		'lock'      => 'sfa_preloads_lock',
		'transient' => 'sfa_preloads_html',
	);
}

/**
 * Seconds until the next scheduled refresh. Anchored to a wall-clock moment
 * rather than a rolling week, so the cache turns over just after the week's
 * data lands instead of drifting with traffic.
 */
function sfa_preload_ttl() {
	$cfg = sfa_preload_config();
	try {
		$tz   = new DateTimeZone( $cfg['timezone'] );
		$now  = new DateTime( 'now', $tz );
		$next = new DateTime( $cfg['day'] . ' ' . $cfg['time'], $tz );
		if ( $now >= $next ) {
			$next->modify( '+7 days' );
		}
		return max( $next->getTimestamp() - $now->getTimestamp(), MINUTE_IN_SECONDS );
	} catch ( Exception $e ) {
		return WEEK_IN_SECONDS;
	}
}

/**
 * Table-only whitelist, deliberately narrower than wp_kses_post. The manifest is
 * ours and arrives over HTTPS, but it is still remote HTML echoed into live
 * articles, so nothing executable can reach the page even if it were tampered
 * with. Verified against the generated tables, so nothing is silently stripped.
 */
function sfa_preload_allowed_tags() {
	$cell = array(
		'scope'   => true,
		'colspan' => true,
		'rowspan' => true,
		'class'   => true,
	);
	return array(
		'table'   => array( 'class' => true ),
		'caption' => array( 'class' => true ),
		'thead'   => array(),
		'tbody'   => array(),
		'tfoot'   => array(),
		'tr'      => array( 'class' => true ),
		'th'      => $cell,
		'td'      => $cell,
		'span'    => array( 'class' => true ),
		'b'       => array(),
		'strong'  => array(),
		'em'      => array(),
		'i'       => array(),
		'abbr'    => array( 'title' => true ),
	);
}

/**
 * Fetch and sanitise the manifest. Returns tool => html, or null on any failure.
 * Sanitising happens once per fetch rather than per render; wp_kses is
 * regex-heavy and the result is identical every time.
 */
function sfa_preload_fetch() {
	$cfg  = sfa_preload_config();
	$resp = wp_remote_get(
		$cfg['url'],
		array(
			'timeout'    => 4,
			'user-agent' => 'SFAStatsPages preload/1.0',
			'headers'    => array( 'Accept' => 'application/json' ),
		)
	);

	$failed = '';
	if ( is_wp_error( $resp ) ) {
		$failed = 'wp_error: ' . $resp->get_error_message();
	} elseif ( 200 !== (int) wp_remote_retrieve_response_code( $resp ) ) {
		$failed = 'http ' . wp_remote_retrieve_response_code( $resp );
	}
	if ( $failed ) {
		error_log( 'sfa_preloads: fetch failed (' . $failed . ') for ' . $cfg['url'] );
		return null;
	}

	$decoded = json_decode( wp_remote_retrieve_body( $resp ), true );
	if ( ! is_array( $decoded ) || empty( $decoded ) ) {
		error_log( 'sfa_preloads: response was not a JSON object for ' . $cfg['url'] );
		return null;
	}

	$clean = array();
	foreach ( $decoded as $key => $html ) {
		if ( is_string( $key ) && is_string( $html ) && '' !== trim( $html ) ) {
			$clean[ sanitize_key( $key ) ] = wp_kses( $html, sfa_preload_allowed_tags() );
		}
	}
	if ( empty( $clean ) ) {
		error_log( 'sfa_preloads: nothing survived sanitising for ' . $cfg['url'] );
		return null;
	}
	return $clean;
}

/**
 * Cached manifest.
 *
 * A transient is the live cache; an option holds the last known good copy, so a
 * brief GitHub outage serves a stale table rather than an empty one. A short
 * lock stops every concurrent request refreshing at once when the cache expires.
 */
function sfa_preload_manifest() {
	static $memo = null;
	if ( null !== $memo ) {
		return $memo;  // one lookup per request, however many shortcodes run
	}

	$cfg    = sfa_preload_config();
	$forced = isset( $_GET['sfa_refresh'] ) && current_user_can( 'edit_posts' );

	if ( ! $forced ) {
		$cached = get_transient( $cfg['transient'] );
		if ( false !== $cached ) {
			$memo = is_array( $cached ) ? $cached : array();
			return $memo;
		}
		if ( false !== get_transient( $cfg['lock'] ) ) {
			$memo = (array) get_option( $cfg['option'], array() );
			return $memo;
		}
	}
	set_transient( $cfg['lock'], 1, $cfg['lock_ttl'] );

	$fresh = sfa_preload_fetch();
	delete_transient( $cfg['lock'] );

	if ( null === $fresh ) {
		$fallback = (array) get_option( $cfg['option'], array() );
		set_transient( $cfg['transient'], $fallback, $cfg['retry'] );
		$memo = $fallback;
		return $memo;
	}

	update_option( $cfg['option'], $fresh, false );  // no autoload
	set_transient( $cfg['transient'], $fresh, sfa_preload_ttl() );
	$memo = $fresh;
	return $memo;
}

/**
 * Styles for the preload table.
 *
 * The shortcode output sits outside .pt-root, so the tool fragment's own CSS
 * cannot reach it. Printed inline on first render rather than enqueued, so the
 * snippet stays self-contained and costs nothing on pages without a shortcode.
 * Every selector is scoped under .sfa-preload; nothing leaks into the theme.
 */
function sfa_preload_styles() {
	static $done = false;
	if ( $done ) {
		return '';
	}
	$done = true;
	/*
	 * Every property is declared on the table elements themselves rather than
	 * left to inherit. Inheritance loses to any theme rule matching th or td
	 * directly, which is how Avada's red heading colour was reaching the team
	 * column. Deliberately plain: only crawlers and no-JS visitors see this.
	 */
	return '<style>'
		. '.sfa-preload{margin:0 0 18px;overflow-x:auto}'
		. '.sfa-preload table,.sfa-preload thead,.sfa-preload tbody,'
		. '.sfa-preload tfoot,.sfa-preload tr,.sfa-preload th,.sfa-preload td,'
		. '.sfa-preload caption,.sfa-preload abbr{'
		. 'font:inherit;color:#111;background:none;border:0;text-align:left;'
		. 'text-transform:none;letter-spacing:normal;text-decoration:none;'
		. 'text-shadow:none;box-shadow:none;vertical-align:middle;margin:0}'
		. '.sfa-preload table{border-collapse:collapse;width:100%;font-size:12px}'
		. '.sfa-preload caption{padding:10px 12px;color:#555;font-size:12px}'
		. '.sfa-preload th,.sfa-preload td{border:1px solid #dde2e8;'
		. 'padding:5px 7px;text-align:center;color:#111}'
		. '.sfa-preload th[scope=row]{text-align:left;font-weight:700;color:#111}'
		. '.sfa-preload thead th{background:#f4f5f7;font-weight:700;color:#111}'
		. '</style>';
}

/**
 * Render one tool's table.
 *
 * data-sfa-preload is what the interactive tool looks for to hide this once it
 * has painted, wherever on the page it sits.
 */
function sfa_preload_render( $tool ) {
	$manifest = sfa_preload_manifest();
	$tool     = sanitize_key( $tool );

	if ( empty( $manifest[ $tool ] ) ) {
		// Never break the page. Leave a trace an editor can find in view-source.
		return '<!-- sfa preload: no table available for ' . esc_html( $tool ) . ' -->';
	}

	return sfa_preload_styles()
		. '<div class="sfa-preload" data-sfa-preload="' . esc_attr( $tool ) . '">'
		. $manifest[ $tool ]  // already sanitised at fetch time
		. '</div>';
}

/*
 * One shortcode per tool, so they read clearly in the CMS. They share the cache
 * above, so the count of shortcodes on a page does not affect request count.
 *
 * To add a tool: copy one of these pairs and match the key in data/preloads.json,
 * then add hideServerPreload() to that tool's render path.
 *
 * To force a refresh: load a page carrying a shortcode with ?sfa_refresh=1 while
 * logged in as an editor, or delete the sfa_preloads_last_good option.
 */
function sfa_preload_personnel_shortcode() {
	return sfa_preload_render( 'personnel_grouping' );
}
add_shortcode( 'sharp_football_personnel', 'sfa_preload_personnel_shortcode' );

function sfa_preload_pace_shortcode() {
	return sfa_preload_render( 'pace' );
}
add_shortcode( 'sharp_football_pace', 'sfa_preload_pace_shortcode' );
