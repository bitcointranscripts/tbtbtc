# TRANSCRIBER TO BITCOIN TRANSCRIPT

This project converts YouTube videos to bitcoinscripts and opens a PR on [bitcoinscript](https://github.com/bitcointranscripts/bitcointranscripts) repo. It uses `youwhisper` to transcribe the videos, then collects meta data about the video using `requests_html`. It then uses the supplied cli arguments and file to open a Pull Request on the [bitcoinscript](https://github.com/bitcointranscripts/bitcointranscripts) repo.

## Steps:

The step-by-step flow for the scripts are:

- transcribe given video and generate the output file

- authenticate the user to GitHub

- fork the transcript repo/use their existing fork, clone it and branch out

- copy the transcript file to the new transcript repo

- commit new file and push  

- then open a PR 

##  Usage

Navigate to the application directory and run the below commands:

`python3 -m venv venv` creates a virtual environment

`source venv/bin/activate` activates the virtual environment

`pip3 install . --use-pep517` to install the application

To check the version:
`tstbtc --version` view the application version

`tstbtc --help` view the application help

`tstbtc {video_id} {directory}` create video transcript supplying the id of the YouTube video and the source/year

`tstbtc {audio_url} {directory} --title {title}` create audio transcript supplying the url of the audio, the source/year and the title of the audio

`pip3 uninstall tstbtc` to uninstall the application

## Testing

To run the tests, run the below command:

`cd test`

To run the unit tests 

`pytest -v -m main -s`

To run the feature tests

`pytest -v -m feature -s`

To run the full test suite

`pytest -v -s`

## OTHER REQUIREMENTS

-  To enable us fork bitcointranscript repo and open a PR, we require you to login into your GitHub account. Kindly install `GITHUB CLI` using the instructions on their repo [here](https://github.com/cli/cli#installation). Following the prompt, please select the below options from the prompt to login:

    -  what account do you want to log into? `Github.com`

    -  what is your preferred protocol for Git operations? `SSH`

    -  Upload your SSH public key to your GitHub account? `skip`

    -  How would you like to authenticate GitHub CLI? `Login with a web browser`

    - copy the generated one-time pass-code and paste in the browser to authenticate if you have enabled 2FA

- Install `FFmpeg`

     - for Mac Os users, run `brew install ffmpeg`

     - for other users, follow the instruction on their [site](https://ffmpeg.org/) to install

##  License
Transcriber to Bitcoin Transcript is released under the terms of the MIT license. See [LICENSE](LICENSE) for more information or see https://opensource.org/licenses/MIT.
