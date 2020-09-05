
// references ip_address and port from dynamically generated ip_address.js

address = ip_address + ':' + port;
const url='http://' + address;

// regularly call get_status() every 1000 ms
var status_interval = setInterval(get_status, 1000);

function vol_toggle_mute(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_toggle_mute");
}

function vol_down(){
    //alert("Vol - from JS");
    //document.getElementById('status0').firstChild.textContent="Vol - from JS";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_down");
}

function vol_up(){
    //alert("Vol + from JS");
    //document.getElementById('status0').firstChild.textContent="Vol + from JS";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("volume_up");
}

function prev_track(){
    //document.getElementById('status0').firstChild.textContent="Pause/Resume Toggle";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("prev_track");
}

function next_track(){
    //document.getElementById('status0').firstChild.textContent="Pause/Resume Toggle";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("next_track");
}

function toggle_pause(){
    //document.getElementById('status0').firstChild.textContent="Pause/Resume Toggle";
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("toggle_pause");
}

function get_status(){
    // This gets called at regular intervals (currently every 1000 ms)
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("get_status");

    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            MAX_LEN = 40;
            NBSP = "\xa0";  // Non-breaking space
            status_text = Http.responseText;
            status_array = status_text.split(/\r?\n/);

            device = status_array[0];
            volume = status_array[1];
            track = status_array[2];
            playback = status_array[3];

            //console.log(status_array)

            len0 = status_array[0].length;

            // status line 0:
            // 0123456789012345678901234567890123456789
            // device_name        vol       ee:ee/dd:dd
            line0_len = device.length + volume.length + playback.length;
            device = "<b>" + device + "</b>";
            if (line0_len >= MAX_LEN - 2) {
                line0 = device + NBSP + volume + NBSP + playback;
            }
            else {
                spacer0_len = Math.floor((MAX_LEN - line0_len) / 2);
                console.log(spacer0_len);
                spacer1_len = MAX_LEN - line0_len - spacer0_len;
                spacer0 = NBSP.repeat(spacer0_len);
                spacer1 = NBSP.repeat(spacer1_len);
                line0 = device + spacer0 + volume + spacer1 + playback;
            }
            //document.getElementById('status0').firstChild.textContent = line0;
            document.getElementById('status0').innerHTML = line0;

            // status line 1:
            // artist - title (album)

            // Initialize a static variable for scroll index
            if (typeof this.scroll_index == 'undefined') {
                this.scroll_index = 0;
            }

            track_status = "";
            full_track_status = "";
            track_len = track.length;
            if (track_len > 0) {
                full_track_status = track.split(' ').join(NBSP);
                if (track_len <= MAX_LEN) {
                    track_status = full_track_status;
                }
                else {
                    extended_track_status = full_track_status + "\xa0\xa0\xa0\xa0";
                    len_extended = extended_track_status.length;
                    // first part
                    end_index = Math.min(...[len_extended, this.scroll_index + MAX_LEN - 1]);
                    first_part = extended_track_status.substring(this.scroll_index, end_index);
                    // second part
                    second_part = "";
                    len_second = MAX_LEN - 1 - first_part.length;
                    if (len_second > 0) {
                        second_part += extended_track_status.substring(0, len_second);
                    }
                    track_status = first_part + second_part;
                    this.scroll_index += 1;
                    if (this.scroll_index > len_extended) {
                        this.scroll_index = 0;
                    }

                    // Initialize a static variable for initial timestamp
                    if (typeof this.init_time == 'undefined') {
                        this.init_time = Date.now();
                    }
                    //console.log(Math.round((Date.now() - self.init_time)/1000), this.scroll_index);
                }
            }
            document.getElementById('status1').firstChild.textContent = track_status;

            // Initialize a static variable for previous track
            if (typeof this.prev_track_status == 'undefined') {
                this.prev_track_status = "";
            }

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
    }
}

function refresh_img(){
    // append #Date.now() as technique to force reload (avoid cache)
    // - also requires some Cache-Control headers from the server
    // see: https://stackoverflow.com/questions/1077041/refresh-image-with-a-new-one-at-the-same-url
    document.getElementById('cover_art').src="cover.jpg#" + Date.now();
}

