#!/usr/bin/python
"""
Created on Thu Oct 27 2016

@author: colinrathbun

Script file to contain all the moving parts for a multithreaded orthogonal
set search to be used on the computational cluster or by other users.
"""

# imports
import pandas as pd
import numpy as np
from numpy import mean, sqrt, eye
from numpy.linalg import norm
from itertools import chain, repeat, combinations, product, permutations
from multiprocessing import Pool

# import matplotlib.pyplot as plt
# plt.rcParams.update({'legend.fontsize': 6})  # make legends format smaller


def buffer_generator(generator, buffer_length):
    '''
    Generator to buffer a longer generator into chunks that can be distributed
    to child processes.
    '''
    more_values = True  # So long as generator starts out with values.
    while more_values:
        sublist = []
        for c in range(buffer_length):
            try:
                sublist.append(next(generator))
            except StopIteration:
                more_values = False
        yield sublist


def check_RMSs_from_submatrix(submatrix):
    '''
    Takes a submatrix and returns the rmsd from the identity matrix.

    TODO: Check whether generating a new identity matrix every time is costly.
    '''
    identityMat = np.eye(submatrix.shape[0])
    submatrix_normd = normalize_vectors(submatrix)
    orthog_submatrix = submatrix_normd.dot(submatrix_normd.T)
    result = RMS_identity(orthog_submatrix, identityMat)

    return result


def run_multiprocess(full_data, dimension, fxn=check_RMSs_from_submatrix,
                     numProcesses=2, threshold=1, buffer_length=1000000,
                     seq_addition=False):
    '''
    Method to run OSF search in multiple processes simultaneously.
    '''
    # if __name__ == '__main__':
    if __name__ == 'orthogonal_set_finder':
        print('trying to run...')
        if seq_addition:
            fxn = check_RMSs_with_seq_addn
        buffer_list = buffer_generator(every_matrix(
            dimension[0], dimension[1], full_data, seq_addition=seq_addition), buffer_length)
        pool = Pool(processes=numProcesses)
        #identityMat = np.eye(dimension)
        full_data_np = full_data.values
        compiled_chunks = []
        for chunk in buffer_list:
            list_of_combinations = [chunk[i::numProcesses] for i in range(
                numProcesses)]
            result_list = pool.starmap(iterate_with_fxn, zip(
                list_of_combinations, repeat(full_data_np.copy()), repeat(fxn)))
            merged_pool = list(chain.from_iterable(result_list))
            compiled_chunks.extend(merged_pool)
        return sorted(compiled_chunks, key=lambda x: x[0])


def clean_raw_data(pdarray):
    """
    Modifies pdarray in place to set any value below 1E3 to 1E3.
    """
    for flux_value in np.nditer(pdarray, op_flags=['readwrite']):
        if flux_value < 1000:
            flux_value[...] = 1000  # using the elipsis will actually set the
            # value in the array


def every_matrix(m, n, pandasArray, seq_addition=False):
    """
    Accepts a pandas dataframe and returns an iterator with every possible
    combination of m rows and n columns via an iterator object. The seq_addition
    switch will output every possible compound addition order.

    TODO m,n should be represented in a tuple in the future.
    """
    index_comb = combinations(range(len(pandasArray.index)), m)
    if seq_addition:
        column_comb = permutations(range(len(pandasArray.columns)), n)
    else:
        column_comb = combinations(range(len(pandasArray.columns)), n)
    index_column_prod = product(index_comb, column_comb)
    return index_column_prod


def get_submatrix(full_data, combination_tuple):
    """
    Accepts a tuple from the every_matrix() iterator to return the actual
    submatrix of the full data (not a copy).
    """
    return full_data[np.ix_(list(combination_tuple[0]), list(
        combination_tuple[1]))]


def RMS_identity(arr, identityMat):
    """
    Returns the average RMS error of the given matrix from the identity matrix.
    """
    square_distance = np.power((arr - identityMat), 2)
    return np.sqrt(np.mean(square_distance))


def normalize_vectors(pandasArray):
    return pandasArray / norm(pandasArray, axis=0)


def check_RMSs(submatrix_indicies, full_data, identityMat):
    '''
    Takes a tuple of the required indicies and the full matrix of data.
    Gets the rms and returns the RMS of the identity matrix as a scalar.
    '''
    submatrix = get_submatrix(full_data, submatrix_indicies)
    submatrix_normd = normalize_vectors(submatrix)
    orthog_submatrix = submatrix_normd.dot(submatrix_normd.T)
    result = RMS_identity(orthog_submatrix, identityMat)

    return result


def check_RMSs_with_seq_addn(submatrix):
    '''
    Takes a submatrix and returns the rmsd from the identity matrix. Defines the
    order of addition as the order that the column indicies are provided. To be
    used in conjunction with every_matrix( ,seq_addition=True).

    TODO: Check whether generating a new identity matrix every time is costly.
    '''
    identityMat = np.eye(submatrix.shape[0])
    # simulate sequential addition
    new_matrix = np.empty(submatrix.shape)
    new_matrix[:, 0] = submatrix[:, 0]
    c = 1
    while c < submatrix.shape[0]:
        new_matrix[:, c] = submatrix[:, c] + new_matrix[:, c - 1]
        c += 1
    # continue with orthogonality calculation
    submatrix_normd = normalize_vectors(new_matrix)
    orthog_submatrix = submatrix_normd.dot(submatrix_normd.T)
    result = RMS_identity(orthog_submatrix, identityMat)

    return result


def get_rms_from_combination(combination, full_data, threshold, identityMat):
    rms = check_RMSs(combination, full_data, identityMat)
    if rms < threshold:
        return (rms, combination)


def iterate_RMSs(list_to_process, full_data, identityMat, threshold=1):
    '''
    Takes a list of tuples of columns and rows to process and the full data
    matrix and iterates through the list, returning the RMS rating and the
    associated matrix. Specify a threshold of 0.15 to only get things that are
    within error of the screen.
    '''
    result_list = []
    for combination in list_to_process:
        result = get_rms_from_combination(
            combination, full_data, threshold, identityMat)
        if result is not None:
            result_list.append(result)

    # result_list = [get_rms_from_combination(
    # combination, full_data, threshold, identityMat) for combination in
    # list_to_process]
    return result_list


def iterate_with_fxn(list_to_process, full_data, fxn):
    '''
    Similar to iterate_RMSs, except able to utilize any function that outputs
    a scalar value for each combination in the data.
    '''
    result_list = []
    for combination in list_to_process:
        submatrix = get_submatrix(full_data, combination)
        result = (fxn(submatrix), combination)
        if result is not None:
            result_list.append(result)
    return result_list


def o_score(rms, shape=(2, 2)):
    worst = np.ones(shape)
    worst_RMS = RMS_identity(worst, np.eye(shape[0]))
    return 2 * (worst_RMS / rms)


def run_singleprocess(full_data, dimension):
    '''
    Method to run OSF search in one processes for testing.
    '''
    full_data_np = full_data.values
    combinations = every_matrix(dimension, dimension, full_data)
    identityMat = np.eye(dimension)
    result_list = iterate_RMSs(combinations, full_data_np, identityMat)
    return sorted(result_list, key=lambda x: x[0])


def run_singleprocess_fxn(full_data, dimension, fxn):
    '''
    Method to run OSF search in one processes for testing. Takes dimension as a
    tuple and a function object to define what operation should be used on the
    input data.
    '''
    full_data_np = full_data.values
    combinations = every_matrix(dimension[0], dimension[1], full_data)
    #identityMat = np.eye(dimension)
    result_list = iterate_with_fxn(combinations, full_data_np, fxn)
    return sorted(result_list, key=lambda x: x[0])


def plot_top_x(sorted_result_list_np, full_data, x=3, filename='test.png'):
    '''
    Plot top x number in the list and save as a png.
    '''
    fig, axs = plt.subplots(1, x)
    c = 0
    for row in sorted_result_list_np[:x]:
        full_data.iloc[list(row[1][0]),
                       list(row[1][1])].plot(ax=axs[c], kind='bar', logy=True,
                                             legend=True)
        c += 1
    fig.savefig(filename)


def format_OSF(sorted_result_list_np, full_data, list_len=1000):
    '''
    Takes a result list from run_singleprocess() or run_multiprocess() and
    formats a DataFrame for export with DataFrame.to_csv().
    '''
    # First, get the numpy back into pandas-readable stuff
    sorted_result_list = []
    compounds = full_data.index
    mutants = full_data.columns
    for rms, cm_tup in sorted_result_list_np:
        c = (compounds[pos] for pos in cm_tup[0])
        m = (mutants[pos] for pos in cm_tup[1])
        sorted_result_list.append((rms, (c, m)))

    pd.set_option('display.float_format', '{:.2E}'.format)  # Forces pandas
    # to use sci-notation.
    working_list = []
    # With an RMS threshold it is possible that the desired result list length
    # is larger than the result list itself.
    if list_len > len(sorted_result_list):
        list_range = range(len(sorted_result_list))
    else:
        list_range = range(list_len)
    for i in list_range:
        subdf = full_data.loc[
            sorted(list(sorted_result_list[i][1][0])),  # Get mutants.
            sorted(list(sorted_result_list[i][1][1]))  # Get compounds.
        ]
        pairs = []
        # This is supposed to search for the intended pairs, but it may not
        # work right when the RMS is so bad that the appropriate pair does
        # not exist.
        for column in subdf.columns:
            row = subdf[column].idxmax()
            pairs.append(column)
            pairs.append(row)
        # If pairs contains duiplicate rows:
        # Then just assign pairs and compounds the default order.
        if len(pairs) != len(set(pairs)):
            pairs = []
            c = 0
            while c < len(subdf.columns):
                pairs.append(subdf.columns[c])
                pairs.append(subdf.index[c])
                c += 1

        working_list.append([
            i + 1,
            o_score(sorted_result_list[i][0], subdf.shape),
            subdf
        ] + pairs)
    pairwise_label = ['1', '1', '2', '2', '3', '3', '4', '4', '5', '5']
    # should look into actually generating this.
    cm_label = ['c', 'm'] * subdf.shape[0]
    fd_labels = ["{}{}".format(cm, p) for cm, p in zip(
        cm_label, pairwise_label)]
    columns = [
        'rank',
        'O score',
        'matrix'
    ] + fd_labels
    resultDF = pd.DataFrame(working_list, columns=columns)
    return resultDF
