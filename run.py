#!/usr/bin/env python3

import os
import logging
import re
import json
import time
import base64
import bs4
import zipfile
import mimetypes
import shutil
import subprocess
import flywheel
import nibabel as nib

log = logging.getLogger('[flywheel/fsl-siena]')


def validate_nifti(nifti_name, nifti_input_path):
    """
    Attempts to load image with nibabel to ensure valid nifti is provided. Checks basename of file
    to ensure it contains no spaces (SIENA/X will not tolerate whitespace). If the basename has spaces,
    the file is copied to a path without whitepaces. The path to the file is returned
    :param nifti_name: str - key describing the nifti file input
    :param nifti_input_path: str - path to the nifti file
    :return: path to file containing no whitespace in the file name
    """
    try:
        # Try loading with nibabel
        nib.load(nifti_input_path)
        log.info('Valid NIfTI file provided {}: {}'.format(nifti_name, nifti_input_path))

    except nib.loadsave.ImageFileError:
        log.error('Invalid NIfTI file provided for input {}: {}'.format(nifti_name, nifti_input_path))
        log.error('Siena/SienaX will not run. Exiting...')
        os.sys.exit(1)

    # Fix spaces in file name
    nifti_folder = os.path.dirname(nifti_input_path)
    nifti_basename = os.path.basename(nifti_input_path).replace(' ', '_')
    nifti_return_path = os.path.join(nifti_folder, nifti_basename)
    # If spaces were fixed, copy file and log info
    if nifti_return_path != nifti_input_path:
        shutil.copyfile(nifti_input_path, nifti_return_path)
        log.info('{} filename contains spaces: {}'.format(nifti_name, nifti_input_path))
        log.info('{} moved to: {}'.format(nifti_name, nifti_return_path))

    return nifti_return_path


def create_options_list(config_dict, manifest_path='/flywheel/v0/manifest.json'):
    """
    generates a list of options to be passed to siena (or sienax) via subprocess
    :param config_dict: config_dict: dict - a dictionary representation of config.json "config"
    :param manifest_path: path to manifest.json
    :return: a list of options parameters to be passed to subprocess
    """
    # Load manifest
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
    # Select options from manifest
    manifest_config = manifest['config']
    # Initialize option list
    option_list = list()
    # Compile regex for flags
    flag_pattern = re.compile('^-[a-zA-Z0-9]{1,2}$')
    for key, option_dict in manifest_config.items():
        option_flag = option_dict.get('id')
        config_value = config_dict.get(key)
        # Skip option if id is not a flag
        if flag_pattern.match(str(option_flag)):
            pass
        else:
            continue
        option_type = option_dict['type']
        # If type is boolean and true, append a flag
        if option_type == 'boolean':
            if config_value == True:
                option_list.append(option_flag)
        elif option_type == 'string':
            # Empty string is the default
            if len(config_value) > 0:
                # These options must be wrapped in quotes
                if key in ['BET', 'S_DIFF', 'S_FAST'] and not config_value.startswith('"'):
                    config_value = '"{}"'.format(config_value)
                # Siena/x still try and run and generate errors on nonsense values like "squirrel", prohibit this
                if key in ['TOP', 'BOTTOM']:
                    number_pattern = re.compile('^[-+]?\d+(?:\.\d+)?')
                    if not number_pattern.match(config_value):
                        log.error('{} value {} is not a number!'.format(key, config_value))
                        log.error('Algorithm will not run. Exiting...')
                        os.sys.exit(1)
                option_list.append(option_flag)
                option_list.append(config_value)
        else:
            log.error('Invalid manifest type for key {} : {}.'.format(key, option_type))
            log.error('Algorithm will not run. Exiting...')
            os.sys.exit(1)
    return option_list


def get_mimetype(filepath_input):
    """
    Guesses mimetype based on filepath_input
    :param filepath_input: (str) path to file
    :return: file_mimetype (str) i.e. 'image/png'
    """
    file_mimetype = mimetypes.guess_type(filepath_input)[0]
    return file_mimetype


def file_to_base64(filepath_input):
    """
    Returns a base64-encoded string representation of the file
    at the input path
    :param filepath_input: (str) path to file
    :return: b64_string (str) utf-8-decoded b64-encoded str
    """
    with open(filepath_input, 'rb') as f:
        b64_string = base64.b64encode(f.read()).decode('utf-8')
    return b64_string


def convert_img_paths_to_b64(input_html_path, output_html_path):
    """
    Reads in an HTML file located at input_html_path and replaces paths
    to images with base64 data when it can locate the images. Writes
    the result to output_html_path
    :param input_html_path: path to html file to be modified
    :param output_html_path: path to which to write modified html file
    :return: output_html_path
    """
    input_html_dir = os.path.dirname(input_html_path)
    try:
        with open(input_html_path, 'r') as func_html_file:
            soup = bs4.BeautifulSoup(func_html_file, 'html.parser')
    except FileNotFoundError:
        log.warning('Could not find {}'.format(input_html_path))
        log.warning('No html files will be modified')
        return None
    # for every image tag
    for img in soup.find_all('img'):
        # get image path from src
        img_path = img.attrs['src']
        img_dir = os.path.dirname(img_path)
        if len(img_dir) == 0:
            img_path = os.path.join(input_html_dir, img_path)
        elif os.path.isfile(img_path):
            pass
        else:
            log.warning('Could not locate image: {}'.format(img_path))
            log.warning('Leaving img src as is.')
            continue
        if os.path.isfile(img_path):
            mimetype = get_mimetype(img_path)
            img.attrs['src'] = 'data:{};base64,{}'.format(mimetype, file_to_base64(img_path))

    with open(output_html_path, 'w') as html_out:
        soup = str(soup).replace(u'\xa0', u' ')
        html_out.write(soup)
    return output_html_path


def parse_report_metadata(report_file_path):
    """
    parses parameters from report.siena, report.viena or report.sienax given a report filepath
    :param report_file_path: (str) path to report.siena/viena/sienax
    :return:
    """
    basename = os.path.basename(report_file_path)
    with open(report_file_path, 'r', encoding='utf-8') as f:
        func_report = f.readlines()
    if basename == 'report.siena':
        report_tuple = ('AREA', 'VOLC', 'RATIO', 'PBVC', 'finalPBVC')
        func_report = [line for line in func_report if line.startswith(report_tuple)]
        report_dict = dict()
        for line in func_report:
            key = line.split()[0]
            value = line.split()[1]
            if (key+'1') in report_dict.keys():
                key = key+'2'
            elif key == 'finalPBVC':
                pass
            else:
                key = key+'1'
            report_dict[key] = value
        return report_dict
    elif basename == 'report.sienax':
        report_tuple = ('GREY', 'WHITE', 'BRAIN')
        func_report = [line for line in func_report if line.startswith(report_tuple)]
        report_dict = dict()
        for line in func_report:
            matter_type_key = line.split()[0]
            volume = line.split()[1]
            unnormalised_volume = line.split()[2]
            report_dict[matter_type_key] = {'volume': volume, 'unnormalised-volume': unnormalised_volume}
        return report_dict
    elif basename == 'report.viena':
        report_dict = dict()
        number_pattern = re.compile('^[-+]?[0-9]+[.]?[0-9]+$')
        for line in func_report:
            split_list = line.split()
            if split_list and number_pattern.match(split_list[-1]):
                key = line.split()[0]
                if len(split_list) == 2:
                    value = line.split()[1]
                else:
                    value = split_list[1:]
                if key in report_dict.keys():
                    key = key + '_real_anaysis'
                else:
                    pass
                report_dict[key] = value
        return report_dict
    else:
        log.warning('Unrecognized report name: {}'.format(basename))
        return None


def remove_nifti_name_paths_and_fix_links(input_html_path, output_html_path):
    """
    Removes broken links to fsl wiki from report.html and removes directories
    from file names with the exception of the invocation command
    :param input_html_path: (str) path to report.html
    :param output_html_path: (str) path to which to write output
    :return:
    """
    with open(input_html_path, 'r', encoding='utf-8') as func_html_file:
        soup = bs4.BeautifulSoup(func_html_file, 'html.parser')
    # remove path from file name
    rep_pattern = re.compile('/flywheel/v0/input/.*/')
    file_rep_list = soup.find_all(text=rep_pattern)
    for item in file_rep_list:
        # Don't delete invocation
        if item.startswith('siena'):
            continue
        replaced = re.sub(rep_pattern, '', item)
        item.replace_with(replaced)
    # delete broken paths
    for item in soup.find_all(('link', 'a')):
        item.replaceWithChildren()
    with open(output_html_path, 'w', encoding='utf-8') as html_out:
        soup = str(soup)
        html_out.write(soup)


def recursive_file_list(directory):
    """
    Recursively lists files in the provided directory (excluding empty directories)
    :param directory: the directory to zip
    :return: a list of paths to individual files in a directory
    """
    # Initialize file list
    file_list = list()
    # Iterate over every base directory
    for base, dirs, files in os.walk(directory):
        for file in files:
            fn = os.path.join(base, file)
            file_list.append(fn)
    return file_list


def zip_most_outputs(directory, archive_name, promote_list):
    """
    zips up files at the directory into <directory>/<archive_name> and removes originals, excuding files in promote_list
    :param directory: (str) path to the directories with contents to zip
    :param archive_name: (str) name of the output archive
    :param promote_list: list of files for which to retain copy outside of archive
    :return:
    """
    # Get list of files
    file_list = recursive_file_list(directory)
    # Determine absolute path for directory
    abspath = os.path.abspath(directory)
    # Format path to archive
    zip_path = os.path.join(abspath, (archive_name+'.zip'))
    # Get full paths for files
    file_list = [os.path.join(abspath, file) for file in file_list]
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_it:
        for file in file_list:
            # Prevent files from being absurdly nested
            zip_path = os.path.relpath(file, directory)
            # Get basename of file
            base = os.path.basename(file)
            zip_it.write(file, zip_path)
            # Don't remove files in promote list
            if base not in promote_list:
                os.remove(file)


def get_subject_code(fw_client, analysis_id):
    """
    Takes and input string and some gear configuration information to get the subject ID
    :param fw_client: the flywheel client
    :param analysis_id: analysis ID from the config/context
    :return:
    """
    analysis_obj = fw_client.get(analysis_id)
    output_subject_code = fw_client.get(analysis_obj.parents.subject).code
    return output_subject_code


if __name__ == '__main__':
    with flywheel.GearContext() as gear_context:
        # Initialize gear logging
        gear_context.init_logging()
        log.info('Starting FSL: SIENA/SIENAX gear...')
        # Initialize client for metadata writing
        fw = gear_context.client
        # Get output filepath
        output_directory = gear_context.output_dir

        # Get config options
        config = gear_context.config
        # Initialize command_list
        command_list = list()
        # Determine if SIENA or SIENAX
        if gear_context.get_input('NIFTI_1') and gear_context.get_input('NIFTI_2'):
            # Add siena command to command list

            command_list.append('siena')
            log.info('Getting FSL {} Configuration...'.format(command_list[0].upper()))
            # Get inputs from manifest
            nifti_1 = gear_context.get_input('NIFTI_1')
            nifti_2 = gear_context.get_input('NIFTI_2')
            ventricle_mask = gear_context.get_input('ventricle_mask')
            # Validate inputs and append to command
            nifti_1_path = validate_nifti('NIFTI_1', nifti_1['location']['path'])
            command_list.append(nifti_1_path)
            nifti_2_path = validate_nifti('NIFTI_2', nifti_2['location']['path'])
            command_list.append(nifti_2_path)

            # Get options from config
            command_options = create_options_list(config)
            # Add optional ventricle mask to options
            if ventricle_mask and '-V' in command_options:
                ventricle_mask_path = validate_nifti('ventricle_mask', ventricle_mask['location']['path'])
                command_options.append('-v')
                command_options.append(ventricle_mask_path)
            elif ventricle_mask and '-V' not in command_options:
                log.error('Ventrical mask provided without selecting "VENT"')
                log.error('Algorithm will not be run. Exiting...')
                os.sys.exit(1)
            # Add options to command list
            command_list = command_list + command_options

        elif gear_context.get_input('NIFTI'):
            # Add sienax command to command list
            command_list.append('sienax')
            log.info('Getting FSL {} Configuration...'.format(command_list[0].upper()))
            # Get inputs from manifest
            nifti = gear_context.get_input('NIFTI')
            # Validate inputs
            nifti_path = validate_nifti('NIFTI', nifti['location']['path'])
            command_list.append(nifti_path)
            lesion_mask = gear_context.get_input('lesion_mask')
            # Get options from config
            command_options = create_options_list(config)
            if lesion_mask:
                lesion_mask_path = validate_nifti('lesion_mask', lesion_mask['location']['path'])
                command_options.append('-lm')
                command_options.append(lesion_mask['location']['path'])
            # Add options to command list
            command_list = command_list + command_options

        else:
            log.error('Invalid manifest.json file provided for FSL SIENA/SIENAX')
            log.error('Algorithm will not run. Exiting...')
            os.sys.exit(1)

        # Add output directory to command list
        command_list.append('-o')
        command_list.append(output_directory)

        # Echo command before running
        echo_command = list()
        echo_command.append('echo')
        echo_command = echo_command + command_list

        log.info('Running FSL {}...'.format(command_list[0].upper()))
        subprocess.run(echo_command)
        # Run command and check exit status
        siena_exit_status = subprocess.check_call(command_list)
        if siena_exit_status == 0:
            # Get subject code and generate timestamp for download-safe renaming
            subject_code = get_subject_code(fw, gear_context.destination['id'])
            timestamp = int(time.time())
            # Specify files to retain outside of the analysis archive
            promote = ['report.{}'.format(command_list[0]), 'report.viena','.metadata.json']
            # Fix report images
            for html_file in ['report.html', 'reportviena.html']:
                html_report_path = os.path.join(output_directory, html_file)
                if os.path.isfile(html_report_path):
                    # Make output file download-safe
                    # Change name so can be downloaded without collisions
                    html_report_name = '{}_{}_{}.html'.format(subject_code, html_file.split('.')[0], timestamp)
                    # Append to promote list
                    promote.append(html_report_name)
                    # Add '.html' back to report path so that it gets type set correctly
                    html_export_path = os.path.join(output_directory, html_report_name)
                    # Convert images to base64
                    convert_img_paths_to_b64(html_report_path, html_export_path)
                    # Fix links and names
                    remove_nifti_name_paths_and_fix_links(html_export_path, html_export_path)
            # Make zip name download-safe
            zip_name = '{}_{}_outputs_{}'.format(subject_code, command_list[0], timestamp)
            zip_most_outputs(output_directory, zip_name, promote)
            # Get metadata
            report_file_list = ['report.{}'.format(command_list[0]), 'report.viena']
            for report in report_file_list:
                report_path = os.path.join(output_directory, report)
                # If the report file exists, parse it
                if os.path.isfile(report_path):
                    report_results = parse_report_metadata(report_path)
                    # Add metadata to analysis info if found
                    if report_results:
                        log.info('{} results: {}'.format(report, report_results))
                        # Use client to get analysis object
                        analysis = fw.get(gear_context.destination['id'])
                        # Add results to analysis object
                        update_dict = dict()
                        update_dict[report.split('.')[1]] = report_results
                        analysis.update_info(update_dict)
                        # Change name so can be downloaded without collisions
                        # Add '.log' to report path so that it gets type set correctly
                        report_name = '{}_{}_{}.log'.format(subject_code, report.split('.')[1], timestamp)
                        export_path = os.path.join(output_directory, report_name)
                        shutil.move(report_path, export_path)

            # Log and exit!
            log.info('FSL {} completed successfully!'.format(command_list[0].upper()))
            os.sys.exit(0)
        else:
            log.info('FSL {} did not execute successfully.'.format(command_list[0].upper()))
            os.sys.exit(siena_exit_status)
