
// references ip_address and port from dynamically generated ip_address.js

address = ip_address + ':' + port;

// if web page is viewing "localhost", then the server requests need to be from
// "localhost" as well rather than the numeric ip address
if (location.hostname == "localhost") {
    url='http://localhost' + ':' + port;
}
else {
    url='http://' + address;
}


// regularly call get_status() every 1000 ms
var status_interval = setInterval(get_status, 1000);


function vol_toggle_mute(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_toggle_mute");

    // refresh status upon server response
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            get_status();
        }
    }
}

function vol_down(){
    //alert("Vol - from JS");
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_down");

    // refresh status upon server response
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            get_status();
        }
    }
}

function vol_up(){
    //alert("Vol + from JS");
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_up");

    // refresh status upon server response
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            get_status();
        }
    }
}

function prev_track(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("prev_track");

    // refresh status upon server response
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            get_status();
        }
    }
}

function next_track(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("next_track");

    // refresh status upon server response
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            get_status();
        }
    }
}

function toggle_pause(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("toggle_pause");

    // refresh status upon server response
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            get_status();
        }
    }
}

function get_status(){
    // This gets called at regular intervals (currently every 1000 ms)
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("get_status");

    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            MAX_LEN = 39;
            NBSP = "\xa0";  // Non-breaking space
            BOLD = "<b>";
            BOLD_END = "</b>";
            ITALIC = "<i>";
            ITALIC_END = "</i>";
            status_text = Http.responseText;
            status_array = status_text.split(/\r?\n/);
//          console.log(status_array);

            function scroll_text(full_track_status) {
                extended_track_status = full_track_status + NBSP.repeat(4);
                len_extended = extended_track_status.length;
                // first part
                end_index = Math.min(...[len_extended, this.scroll_index + MAX_LEN]);
                first_part = extended_track_status.substring(this.scroll_index, end_index);
                // second part
                second_part = "";
                len_second = MAX_LEN - first_part.length;
                if (len_second > 0) {
                    second_part += extended_track_status.substring(0, len_second);
                }
                track_status = first_part + second_part;
                this.scroll_index += 1;
                if (this.scroll_index > len_extended) {
                    this.scroll_index = 0;
                }

                return track_status;
            }

            [connected, device, volume, artist, title, album, current_time, duration, paused] = status_array;

            if (current_time.length > 0 && duration.length > 0) {
                playback_len = current_time.length + duration.length + 1;
                playback = current_time + BOLD + "/" + BOLD_END + duration;
            }
            else {
                playback = "";
                playback_len = playback.length;
            }

            // status line 0:
            // 0123456789012345678901234567890123456789
            // device_name        vol       ee:ee/dd:dd
            line0_len = device.length + volume.length + playback_len;
            device = BOLD + device + BOLD_END;
            if (connected == "1") {
                if (line0_len >= MAX_LEN - 2) {
                    line0 = device + NBSP + volume + NBSP + playback;
                }
                else {
                    spacer0_len = Math.floor((MAX_LEN - line0_len) / 2);
                    spacer1_len = MAX_LEN - line0_len - spacer0_len;
                    spacer0 = NBSP.repeat(spacer0_len);
                    spacer1 = NBSP.repeat(spacer1_len);
                    line0 = device + spacer0 + volume + spacer1 + playback;
    //              console.log("Spacers:" + spacer0_len + spacer1_len)
                }
            }
            else {
                DISCONNECTED_CH = "\u2716"; // ✖
                line0 = device + " " + DISCONNECTED_CH;
            }
            document.getElementById('status0').innerHTML = line0;

            // status line 1:
            // artist - title (album)

            // Initialize a static variable for scroll index
            if (typeof this.scroll_index == 'undefined') {
                this.scroll_index = 0;
            }

            track_status = "";
            full_track_status = "";

            if (connected == "1") {
                // "ARTIST - TITLE (ALBUM)"
                // Unfortunately: scroller implmentations doesn't like formatted text...
                // track = BOLD + artist + BOLD_END + " - " + title + ITALIC + " (" + album + ")" + ITALIC_END;
                track = artist + " - " + title + " (" + album + ")";
                track_len = artist.length + title.length + album.length + 6;
                if (track_len > 0) {
                    full_track_status = track.split(' ').join(NBSP);
                    if (track_len <= MAX_LEN) {
                        track_status = full_track_status;
                    }
                    else {
                        track_status = scroll_text(full_track_status);
                    }
                }
            }
            document.getElementById('status1').innerHTML = track_status;

            // set play/pause button image appropriately
            if (paused == "0") {
                document.getElementById('toggle_pause_img').src = "imgs/icons8-pause-button-96.png";
            }
            else {
                document.getElementById('toggle_pause_img').src = "imgs/icons8-circled-play-96.png";
            }

            // Initialize a static variable for previous track
            if (typeof this.prev_track_status == 'undefined') {
                this.prev_track_status = "";
            }

            if (connected == "1") {
                // refresh img if track has changed
                if (this.prev_track_status.localeCompare(full_track_status) != 0) {
                    // filter out spurious assignments of 'undefined' 
                    // (not sure why we get these...)
                    if ("undefined".localeCompare(full_track_status) != 0) {
                        console.log("Track status changed to: " + full_track_status)
                        refresh_img();
                        this.prev_track_status = full_track_status;
                    }
                }
            }
            else {
                disable_img();
            }
        }
    }
}

function refresh_img(){
    // append #Date.now() as technique to force reload (avoid cache)
    // - also requires some Cache-Control headers from the server
    // see: https://stackoverflow.com/questions/1077041/refresh-image-with-a-new-one-at-the-same-url
    document.getElementById('cover_art').src="cover.jpg#" + Date.now();
    document.getElementById('cover_art').style.visibility = 'visible';
}

function disable_img(){
    document.getElementById('cover_art').style.visibility = 'hidden';
}

