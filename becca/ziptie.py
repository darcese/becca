"""
The Ziptie class.
"""

from __future__ import print_function
import numpy as np
import matplotlib.pyplot as plt

import becca.tools as tools
import becca.ziptie_numba as nb


class Ziptie(object):
    """
    An incremental unsupervised clustering algorithm.

    Input channels are clustered together into mutually co-active sets.
    A helpful metaphor is bundling cables together with zip ties.
    Cables that carry related signals are commonly co-active,
    and are grouped together. Cables that are co-active with existing
    bundles can be added to those bundles. A single cable may be ziptied
    into several different bundles. Co-activity is estimated
    incrementally, that is, the algorithm updates the estimate after
    each new set of signals is received.

    When stacked with other levels,
    zipties form a sparse deep neural network (DNN).
    This DNN has the extremely desirable characteristic of
    l-0 sparsity--the number of non-zero weights are minimized.
    The vast majority of weights in this network are zero,
    and the rest are one.
    This makes sparse computation feasible and allows for
    straightforward interpretation and visualization of the
    features.
    """

    def __init__(
            self,
            n_cables=16,
            n_bundles=None,
            name=None,
            threshold=1e4,
            debug=False,
    ):
        """
        Initialize the ziptie, pre-allocating data structures.

        Parameters
        ----------
        debug : boolean, optional
            Indicate whether to print informative status messages
            during execution. Default is False.
        n_bundles : int, optional
            The number of bundle outputs from the Ziptie.
        n_cables : int
            The number of inputs to the Ziptie.
        name : str, optional
            The name assigned to the Ziptie.
            Default is 'ziptie'.
        threshold : float
            The point at which to nucleate a new bundle or
            agglomerate to an existing one.
        """
        # name : str
        #     The name associated with the Ziptie.
        if name is None:
            self.name = 'ziptie'
        else:
            self.name = name
        # debug : boolean
        #     Indicate whether to print informative status messages
        #     during execution.
        self.debug = debug
        # n_cables : int
        #     The maximum number of cable inputs allowed.
        self.n_cables = n_cables
        # n_bundles : int
        #     The number of bundle outputs.
        if not n_bundles:
            self.n_bundles = self.n_cables
        else:
            self.n_bundles = n_bundles

        # nucleation_threshold : float
        #     Threshold above which nucleation energy results in nucleation.
        self.nucleation_threshold = threshold
        # agglomeration_threshold
        #     Threshold above which agglomeration energy results
        #     in agglomeration.
        self.agglomeration_threshold = self.nucleation_threshold
        # activity_threshold : float
        #     Threshold below which input activity is teated as zero.
        #     By ignoring the small activity values,
        #     computation gets much faster.
        self.activity_threshold = .1
        # bundles_full : bool
        #     If True, all the bundles in the Ziptie are full
        #     and learning stops. This is another way to speed up
        #     computation.
        self.bundles_full = False
        # cable_activities : array of floats
        #     The current set of input actvities.
        self.cable_activities = np.zeros(self.n_cables)
        # bundle_activities : array of floats
        #     The current set of bundle activities.
        self.bundle_activities = np.zeros(self.n_bundles)
        # nonbundle_activities : array of floats
        #     The set of input activities that do not contribute
        #     to any of the current bundle activities.
        self.nonbundle_activities = np.zeros(self.n_cables)

        # bundle_map_size : int
        #     The maximum number of non-zero entries in the bundle map.
        self.bundle_map_size = 8
        # bundle_map_cols, bundle_map_rows : array of ints
        #     To represent the sparse 2D bundle map, a pair of row and col
        #     arrays are used. Rows are bundle indices, and cols are
        #     feature indices.  The bundle map shows which cables
        #     are zipped together to form which bundles.
        self.bundle_map_rows = -np.ones(self.bundle_map_size).astype(int)
        self.bundle_map_cols = -np.ones(self.bundle_map_size).astype(int)
        # n_map_entries: int
        #     The total number of bundle map entries that
        #     have been created so far.
        self.n_map_entries = 0
        # agglomeration_energy: 2D array of floats
        #     The accumulated agglomeration energy for each bundle-cable pair.
        self.agglomeration_energy = np.zeros((self.n_bundles,
                                              self.n_cables))
        # agglomeration_mask: 2D array of floats
        #     A binary array indicating which cable-bundle
        #     pairs are allowed to accumulate
        #     energy and which are not. Some combinations are
        #     disallowed because they result in redundant bundles.
        self.agglomeration_mask = np.ones((self.n_bundles,
                                           self.n_cables))
        # nucleation_energy: 2D array of floats
        #     The accumualted nucleation energy associated
        #     with each cable-cable pair.
        self.nucleation_energy = np.zeros((self.n_cables,
                                           self.n_cables))
        # nucleation_mask: 2D array of floats
        #     A binary array indicating which cable-cable
        #     pairs are allowed to accumulate
        #     energy and which are not. Some combinations are
        #     disallowed because they result in redundant bundles.
        self.nucleation_mask = np.ones((self.n_cables,
                                        self.n_cables))

    def featurize(self, new_cable_activities, bundle_weights=None):
        """
        Calculate how much the cables' activities contribute to each bundle.

        Find bundle activities by taking the minimum input value
        in the set of cables in the bundle. The bulk of the computation
        occurs in ziptie_numba.find_bundle_activities.
        """
        self.cable_activities = new_cable_activities.copy()
        #self.nonbundle_activities = self.cable_activities.copy()
        #self.bundle_activities = np.zeros(self.n_bundles)
        self.bundle_activities = 1e3 * np.ones(self.n_bundles)
        if bundle_weights is None:
            bundle_weights = np.ones(self.n_bundles)
        if self.n_map_entries > 0:
            #nb.find_bundle_activities(
            #    self.bundle_map_rows[:self.n_map_entries],
            #    self.bundle_map_cols[:self.n_map_entries],
            #    self.nonbundle_activities,
            #    self.bundle_activities,
            #    bundle_weights, self.activity_threshold)
            for i_map_entry in range(self.n_map_entries):
                i_bundle = self.bundle_map_rows[i_map_entry]
                i_cable = self.bundle_map_cols[i_map_entry]
                self.bundle_activities[i_bundle] = (
                    np.minimum(self.bundle_activities[i_bundle],
                               self.cable_activities[i_cable]))
        self.bundle_activities[np.where(self.bundle_activities == 1e3)] = 0.
        self.bundle_activities *= bundle_weights
        # The residual cable_activities after calculating
        # bundle_activities are the nonbundle_activities.
        # Sparsify them by setting all the small values to zero.
        #self.nonbundle_activities[np.where(self.nonbundle_activities <
        #                                   self.activity_threshold)] = 0.
        # return self.nonbundle_activities, self.bundle_activities
        return self.bundle_activities


    def learn(self, cable_activities):
        """
        Update co-activity estimates and calculate bundle activity

        This step combines the projection of cables activities
        to bundle activities together with using the cable activities
        to incrementally train the Ziptie.

        Parameters
        ----------
        none

        Returns
        -------
        none
        """
        if not self.bundles_full:
            self._create_new_bundles(cable_activities)
        if not self.bundles_full:
            self._grow_bundles(cable_activities)
        return


    def _create_new_bundles(self, cable_activities):
        """
        If the right conditions have been reached, create a new bundle.
        """
        # Incrementally accumulate nucleation energy.
        nb.nucleation_energy_gather(cable_activities,
                                    self.nucleation_energy,
                                    self.nucleation_mask)

        # Don't accumulate nucleation energy between a cable and itself
        ind = np.arange(self.cable_activities.size).astype(int)
        self.nucleation_energy[ind, ind] = 0.

        results = -np.ones(3)
        nb.max_dense(self.nucleation_energy, results)
        max_energy = results[0]
        cable_index_a = int(results[1])
        cable_index_b = int(results[2])

        # Add a new bundle if appropriate
        if max_energy > self.nucleation_threshold:
            self.bundle_map_rows[self.n_map_entries] = self.n_bundles
            self.bundle_map_cols[self.n_map_entries] = cable_index_a
            self.increment_n_map_entries()
            self.bundle_map_rows[self.n_map_entries] = self.n_bundles
            self.bundle_map_cols[self.n_map_entries] = cable_index_b
            self.increment_n_map_entries()

            # Reset the accumulated nucleation and agglomeration energy
            # for the two cables involved.
            self.nucleation_energy[cable_index_a, :] = 0.
            self.nucleation_energy[cable_index_b, :] = 0.
            self.nucleation_energy[:, cable_index_a] = 0.
            self.nucleation_energy[:, cable_index_b] = 0.
            self.agglomeration_energy[:, cable_index_a] = 0.
            self.agglomeration_energy[:, cable_index_b] = 0.

            # Update nucleation_mask to prevent the two cables from
            # accumulating nucleation energy in the future.
            self.nucleation_mask[cable_index_a, cable_index_b] = 0.
            self.nucleation_mask[cable_index_b, cable_index_a] = 0.

            # Update agglomeration_mask to account for the new bundle.
            # The new bundle should not accumulate agglomeration energy
            # with any of the cables that any of its constituent cables
            # are blocked from nucleating with.
            blocked_a = np.where(self.nucleation_mask[cable_index_a, :] == 0.)
            blocked_b = np.where(self.nucleation_mask[cable_index_b, :] == 0.)
            blocked = np.union1d(blocked_a[0], blocked_b[0])
            self.agglomeration_mask[self.n_bundles, blocked] = 0.

            self.n_bundles += 1
            if self.debug:
                print(' '.join([
                    '    ', self.name,
                    'bundle', str(self.n_bundles),
                    'added with cables', str(cable_index_a),
                    str(cable_index_b)
                ]))

            # Check whether the Ziptie's capacity has been reached.
            if self.n_bundles == self.n_bundles:
                self.bundles_full = True

    def _grow_bundles(self, cable_activities):
        """
        Update an estimate of co-activity between all cables.
        """
        # Incrementally accumulate agglomeration energy.
        nb.agglomeration_energy_gather(self.bundle_activities,
                                       cable_activities,
                                       self.n_bundles,
                                       self.agglomeration_energy,
                                       self.agglomeration_mask)

        # Don't accumulate agglomeration energy between cables already
        # in the same bundle
        val = 0.
        if self.n_map_entries > 0:
            nb.set_dense_val(self.agglomeration_energy,
                             self.bundle_map_rows[:self.n_map_entries],
                             self.bundle_map_cols[:self.n_map_entries],
                             val)

        results = -np.ones(3)
        nb.max_dense(self.agglomeration_energy, results)
        max_energy = results[0]
        cable_index = int(results[2])
        bundle_index = int(results[1])

        # Add a new bundle if appropriate
        if max_energy > self.agglomeration_threshold:
            # Find which cables are in the new bundle.
            cables = [cable_index]
            for i in range(self.n_map_entries):
                if self.bundle_map_rows[i] == bundle_index:
                    cables.append(self.bundle_map_cols[i])

            # TODO: Check whether masks make this step obsolete
            '''
            # Check whether the agglomeration is already in the bundle map.
            candidate_bundles = np.arange(self.n_bundles)
            for cable in cables:
                matches = np.where(self.bundle_map_cols == cable)[0]
                candidate_bundles = np.intersect1d(
                    candidate_bundles,
                    self.bundle_map_rows[matches],
                    assume_unique=True)
            if candidate_bundles.size != 0:
                # The agglomeration has already been used to create a
                # bundle. Ignore and reset they count. This can happen
                # under normal circumstances, because of how nonbundle
                # activities are calculated.
                self.agglomeration_energy[bundle_index, cable_index] = 0.
                return
            '''

            # Make a copy of the growing bundle.
            for i in range(self.n_map_entries):
                if self.bundle_map_rows[i] == bundle_index:
                    self.bundle_map_rows[self.n_map_entries] = self.n_bundles
                    self.bundle_map_cols[self.n_map_entries] = (
                        self.bundle_map_cols[i])
                    self.increment_n_map_entries()
            # Add in the new cable.
            self.bundle_map_rows[self.n_map_entries] = self.n_bundles
            self.bundle_map_cols[self.n_map_entries] = cable_index
            self.increment_n_map_entries()

            # Reset the accumulated nucleation and agglomeration energy
            # for the two cables involved.
            self.nucleation_energy[cable_index, :] = 0.
            self.nucleation_energy[cable_index, :] = 0.
            self.nucleation_energy[:, cable_index] = 0.
            self.nucleation_energy[:, cable_index] = 0.
            self.agglomeration_energy[:, cable_index] = 0.
            self.agglomeration_energy[bundle_index, :] = 0.

            # Update agglomeration_mask to account for the new bundle.
            # The new bundle should not accumulate agglomeration energy with
            # 1) the cables that its constituent cable
            #    are blocked from nucleating with or
            # 2) the cables that its constituent bundle
            #    are blocked from agglomerating with.
            blocked_cable = np.where(
                self.nucleation_mask[cable_index, :] == 0.)
            blocked_bundle = np.where(
                self.agglomeration_mask[bundle_index, :] == 0.)
            blocked = np.union1d(blocked_cable[0], blocked_bundle[0])
            self.agglomeration_energy[self.n_bundles, blocked] = 0.

            self.n_bundles += 1

            if self.debug:
                print(' '.join(['    ', self.name,
                                'bundle', str(self.n_bundles),
                                'added: bundle', str(bundle_index),
                                'and cable', str(cable_index)]))

            # Check whether the Ziptie's capacity has been reached.
            if self.n_bundles == self.n_bundles:
                self.bundles_full = True

    def update_masks(self, child_index, parent_index):
        """
        Update energy masks when a new cable is added.

        The new cable inherits all the blocked agglomerations and
        nucleations of its parent cable.

        @param child_index: int
        @param parent_index: list of int
        """
        self.nucleation_mask[child_index, child_index] = 0.
        self.nucleation_mask[parent_index, child_index] = 0.
        self.nucleation_mask[child_index, parent_index] = 0.

    def increment_n_map_entries(self):
        """
        Add one to n_map entries and grow the bundle map as needed.
        """
        self.n_map_entries += 1
        if self.n_map_entries >= self.bundle_map_size:
            self.bundle_map_size *= 2
            self.bundle_map_rows = tools.pad(self.bundle_map_rows,
                                             self.bundle_map_size,
                                             val=-1, dtype='int')
            self.bundle_map_cols = tools.pad(self.bundle_map_cols,
                                             self.bundle_map_size,
                                             val=-1, dtype='int')


    def get_index_projection(self, bundle_index):
        """
        Project bundle_index down to its cable indices.

        Parameters
        ----------
        bundle_index : int
            The index of the bundle to project onto its constituent cables.

        Returns
        -------
        projection : array of floats
            An array of zeros and ones, representing all the cables that
            contribute to the bundle. The values projection
            corresponding to all the cables that contribute are 1.
        """
        projection = np.zeros(self.n_cables)
        for i in range(self.n_map_entries):
            if self.bundle_map_rows[i] == bundle_index:
                projection[self.bundle_map_cols[i]] = 1.
        return projection


    def get_index_projection_cables(self, bundle_index):
        """
        Project bundle_index down to its cable indices.

        Parameters
        ----------
        bundle_index : int
            The index of the bundle to project onto its constituent cables.

        Returns
        -------
        projection_indices : array of ints
            An array of cable indices, representing all the cables that
            contribute to the bundle.
        """
        projection = []
        for i in range(self.n_map_entries):
            if self.bundle_map_rows[i] == bundle_index:
                projection.append(self.bundle_map_cols[i])
        projection_indices = np.array(projection)
        return projection_indices


    def project_bundle_activities(self, bundle_activities):
        """
        Take a set of bundle activities and project them to cable activities.
        """
        cable_activities = np.zeros(self.n_cables)
        for i in range(self.n_map_entries):
            i_bundle = self.bundle_map_rows[i]
            i_cable = self.bundle_map_cols[i]
            cable_activities[i_cable] = max(cable_activities[i_cable],
                                            bundle_activities[i_bundle])
        return cable_activities


    def visualize(self):
        """
        Turn the state of the Ziptie into an image.
        """
        print(self.name)
        # First list the bundles and the cables in each.
        i_bundles = self.bundle_map_rows[:self.n_map_entries]
        i_cables = self.bundle_map_cols[:self.n_map_entries]
        i_bundles_unique = np.unique(i_bundles)
        if i_bundles_unique is not None:
            for i_bundle in i_bundles_unique:
                b_cables = list(np.sort(i_cables[np.where(
                    i_bundles == i_bundle)[0]]))
                print(' '.join(['    bundle', str(i_bundle),
                                'cables:', str(b_cables)]))

        plot = False
        if plot:
            if self.n_map_entries > 0:
                # Render the bundle map.
                bundle_map = np.zeros((self.n_cables,
                                       self.n_bundles))
                nb.set_dense_val(bundle_map,
                                 self.bundle_map_rows[:self.n_map_entries],
                                 self.bundle_map_cols[:self.n_map_entries], 1.)
                tools.visualize_array(bundle_map,
                                      label=self.name + '_bundle_map')

                # Render the agglomeration energy.
                label = '_'.join([self.name, 'agg_energy'])
                tools.visualize_array(self.agglomeration_energy, label=label)
                plt.xlabel(str(np.max(self.agglomeration_energy)))

                # Render the nucleation energy.
                label = '_'.join([self.name, 'nuc_energy'])
                tools.visualize_array(self.nucleation_energy, label=label)
                plt.xlabel(str(np.max(self.nucleation_energy)))
