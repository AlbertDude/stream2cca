
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
var status_interval;
set_status_interval();

function set_status_interval(){
    status_interval = setInterval(get_status, 1000);
}

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

function play_pause_resume(){
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("play_pause_resume");

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
                line0 = device + " " + DISCONNECTED_CH + " Disconnected. Click to Scan Devices " + DISCONNECTED_CH;
            }
            document.getElementById('status0').innerHTML = line0;

            if ((connected == "0") || (playback == "")){
                document.getElementById('play_pause_img').src = "imgs/ipod-old.png";
            }
            else {
                // set play/pause button image appropriately
                if (paused == "0") {
                    document.getElementById('play_pause_img').src = "imgs/icons8-pause-button-96.png";
                }
                else {
                    document.getElementById('play_pause_img').src = "imgs/icons8-circled-play-96.png";
                }
            }


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
                        //console.log("Track status changed to: " + full_track_status)
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

var device_text;

function scan_devices(){
    // hide dynamicDropdown if it's already showing and skip the scan
    if (showingDynamicDropdown == 1) {
        hideDynamicDropdown();
        return;
    }

    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("scan_devices");

    // Change the status0 display message
    NBSP = "\xa0";  // Non-breaking space
    numSpaces = 14;
    document.getElementById('status0').innerHTML = NBSP.repeat(numSpaces) + "Scanning..." + NBSP.repeat(numSpaces);

    // set callback to handle server response
    clearInterval(status_interval); // disable the regular status pings until the response arrives
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            device_text = Http.responseText;
            //console.log("scan_devices() DONE: " + device_text)
            showDynamicDropdown()

            set_status_interval(); // done. re-enable regular status pings
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
    //document.getElementById('cover_art').style.visibility = 'hidden';
    document.getElementById('cover_art').src="imgs/noise.jpg";
    document.getElementById('cover_art').style.visibility = 'visible';
}

var showingDynamicDropdown = 0;

// Dynamic generation of dropdown
function showDynamicDropdown() {
    //Create the new dropdown menu
    var whereToPut = document.getElementById('dynamicDropdownDiv');
    var dynamicDropdown = document.createElement('select');
    dynamicDropdown.setAttribute('class', "dropdown-content");  // TODO: doesn't seem to do anything
    dynamicDropdown.setAttribute('id', "dynamicDropdown");
    dynamicDropdown.setAttribute('onchange', "deviceSelected();");
    whereToPut.appendChild(dynamicDropdown);

    //Add dummy option
    //- the first option isn't selectable so don't want to put a real one there
    var optionDummy=document.createElement("option");
    optionDummy.setAttribute('disabled', "disabled");
    optionDummy.setAttribute('selected', "selected");
    optionDummy.text="<-- Select device -->";
    dynamicDropdown.add(optionDummy, dynamicDropdown.options[null]);

    function createOption(index, device_name){
        var option = document.createElement("option");
        option.setAttribute('value', index);
        option.text = device_name;
        return option;
    }

    // add option per device
    device_array = device_text.split(/\r?\n/);
    for( const device_spec of device_array){
        [index, device_name] = device_spec.split(",");
        //console.log(index, device_name)

        option = createOption(index, device_name);
        dynamicDropdown.add(option, dynamicDropdown.options[null]);
    }

    showingDynamicDropdown = 1;
    document.getElementById('scanDevicesTooltip').innerHTML = "Click to Close Device Selector";
}

function hideDynamicDropdown() {
    var d = document.getElementById('dynamicDropdownDiv');

    var oldmenu = document.getElementById('dynamicDropdown');

    d.removeChild(oldmenu);
    showingDynamicDropdown = 0;
    document.getElementById('scanDevicesTooltip').innerHTML = "Click to Scan Devices";
}

function deviceSelected() {
    var dynamicDropdown = document.getElementById('dynamicDropdown');
    deviceNum = dynamicDropdown.value;

    // send selected device to server!!
    Http = new XMLHttpRequest();
    Http.open("POST", url, true);
    Http.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    Http.send("select_device "+deviceNum);

    // refresh status upon server response
    Http.onreadystatechange = (e) => {
        if (Http.readyState === XMLHttpRequest.DONE) {
            get_status();
        }
    }

    hideDynamicDropdown()
    //console.log("deviceSelected: " + deviceNum);
}
