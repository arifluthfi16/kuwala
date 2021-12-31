import os
import subprocess
import zipfile
from threading import Thread
from kuwala.common.python_utils.src.FileDownloader import download_file


def download_demo():
    script_dir = os.path.dirname(__file__)
    file_path = os.path.join(script_dir, f'../../../tmp/kuwala/db/neo4j.zip')
    download_file(url='https://kuwala-demo.s3.eu-central-1.amazonaws.com/neo4j.zip', path=file_path)

    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(file_path.split('/neo4j.zip')[0])

    os.remove(file_path)


def run_command(command: [str], exit_keyword=None):
    process = subprocess.Popen(
        command,
        bufsize=1,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        shell=True
    )
    thread_result = dict(hit_exit_keyword=False)

    def print_std(std, result):
        while True:
            line = std.readline()

            if len(line.strip()) > 0:
                print(line if 'Stage' not in line and '%' not in line else line.strip(), end='\r')

            if exit_keyword is not None and exit_keyword in line:
                result['hit_exit_keyword'] = True

                break

            return_code = process.poll()

            if return_code is not None:
                if return_code != 0:
                    return RuntimeError()

                break

    stdout_thread = Thread(target=print_std, args=(process.stdout, thread_result,), daemon=True)
    stderr_thread = Thread(target=print_std, args=(process.stderr, thread_result,), daemon=True)

    stdout_thread.start()
    stderr_thread.start()

    while stdout_thread.is_alive() and stderr_thread.is_alive():
        pass

    if thread_result['hit_exit_keyword']:
        return process


def run_osm_poi_pipeline(url, continent, country, country_region):
    continent_arg = f'--continent={continent}' if continent else ''
    country_arg = f'--country={country}' if country else ''
    country_region_arg = f'--country_region={country_region}' if country_region else ''

    run_command([f'docker-compose run --rm osm-poi --action=download --url={url} {continent_arg} {country_arg} '
                 f'{country_region_arg}'])
    run_command([f'docker-compose run --rm osm-parquetizer java -jar target/osm-parquetizer-1.0.1-SNAPSHOT.jar '
                 f'{continent_arg} {country_arg} {country_region_arg}'])
    run_command([f'docker-compose run --rm osm-poi --action=process {continent_arg} {country_arg} '
                 f'{country_region_arg}'])


def run_google_poi_pipeline(continent, country, country_region):
    continent_arg = f'--continent={continent}' if continent else ''
    country_arg = f'--country={country}' if country else ''
    country_region_arg = f'--country_region={country_region}' if country_region else ''
    scraping_api_process = run_command(f'docker-compose --profile google-poi-scraper up', exit_keyword='Running')

    run_command([f'docker-compose run --rm google-poi-pipeline {continent_arg} {country_arg} {country_region_arg}'])
    scraping_api_process.terminate()


def run_population_density_pipeline(continent, country, demographic_groups, population_density_update_date):
    continent_arg = f'--continent={continent}' if continent else ''
    country_arg = f'--country={country}' if country else ''
    demographic_groups_arg = f'--demographic_groups={demographic_groups}' if demographic_groups else ''
    population_density_update_date_arg=f'--population_density_date={population_density_update_date}' if population_density_update_date else ''

    run_command([f'docker-compose run --rm population-density {continent_arg} {country_arg} {demographic_groups_arg} {population_density_update_date_arg}'])


def run_neo4j_importer(continent, country, country_region):
    continent_arg = f'--continent={continent}' if continent else ''
    country_arg = f'--country={country}' if country else ''
    country_region_arg = f'--country_region={country_region}' if country_region else ''
    neo4j_process = run_command(f'docker-compose --profile core up', exit_keyword='Started.')

    run_command([f'docker-compose run --rm neo4j-importer {continent_arg} {country_arg} {country_region_arg}'])
    neo4j_process.terminate()


def run_pipelines(pipelines: [str], selected_region: dict):
    continent = selected_region['continent']
    country = selected_region['country']
    country_region = selected_region['country_region']
    updated_date=selected_region['population_density_date']

    if 'google-poi' in pipelines or 'osm-poi' in pipelines:
        run_osm_poi_pipeline(selected_region['osm_url'], continent, country, country_region)

    if 'google-poi' in pipelines:
        run_google_poi_pipeline(continent, country, country_region)

    if 'population-density' in pipelines:
        run_population_density_pipeline(continent, country, selected_region['demographic_groups'], updated_date)

    run_neo4j_importer(continent, country, country_region)
    run_command(['docker-compose down --remove-orphans'])
