Chat-Poll-with-OBS is distributed under the GPL V2 licesne

For information on how to setup and use Chat-Poll see setup-guide.txt

Contact me directly on Discord @drakerp2

Chat-Poll utilizes localhost port 36457, 36458, 36459, and 36460, which are designated as unassigned by the IANA (https://www.iana.org/assignments/service-names-port-numbers/service-names-port-numbers.xhtml?search=5&page=45)
	currently there is no formal way to change these ports (though the feature is planned), however you can manually change them in the python files

See todo file for planned features

Known Issues:
	Minor race conditions are present, mitigate as much as possible, but refactor to threading is planned to make the system more uniform and less volitile.
	Proccesses may not fully close on program crash
