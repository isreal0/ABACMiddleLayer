package com.yasusoft.abacml;

import java.io.File;

import junit.framework.Test;
import junit.framework.TestCase;
import junit.framework.TestSuite;

import org.wso2.balana.finder.impl.FileBasedPolicyFinderModule;

/**
 * Exercises Evaluate_ABAC_Decision against an isolated UOA Canvas LMS test
 * policy (src/test/resources/uoa-canonical-policies), independent of the
 * production policy at abacml/resources/abacmlpolicy.xml.
 *
 * The policy directory system property is set once in a static initializer
 * so it takes effect before Balana.getInstance() is first called in this
 * JVM (Balana caches its configuration on first use).
 */
public class UOACanonicalDecisionTest extends TestCase
{
    static {
        try {
            String policyDir = new File("src/test/resources/uoa-canonical-policies").getCanonicalPath();
            System.setProperty(FileBasedPolicyFinderModule.POLICY_DIR_PROPERTY, policyDir);
        } catch (Exception e) {
            throw new RuntimeException("Could not resolve test policy directory", e);
        }
    }

    public UOACanonicalDecisionTest(String testName) {
        super(testName);
    }

    public static Test suite() {
        return new TestSuite(UOACanonicalDecisionTest.class);
    }

    public void testPermit_SameDepartmentSufficientClearance() {
        String decision = ABACML.Evaluate_ABAC_Decision(
                "alice", "student", "ComputerScience", 3,
                "STUDENT_GRADES", "alice", "ComputerScience", 2,
                "SELECT",
                "campus", 10);
        assertEquals("Permit", decision);
    }

    public void testDeny_DifferentDepartment() {
        String decision = ABACML.Evaluate_ABAC_Decision(
                "bob", "student", "Engineering", 3,
                "STUDENT_GRADES", "alice", "ComputerScience", 2,
                "SELECT",
                "campus", 10);
        assertEquals("Deny", decision);
    }

    public void testDeny_InsufficientClearance() {
        String decision = ABACML.Evaluate_ABAC_Decision(
                "carol", "student", "ComputerScience", 1,
                "STUDENT_GRADES", "alice", "ComputerScience", 2,
                "SELECT",
                "campus", 10);
        assertEquals("Deny", decision);
    }

    public void testNotApplicable_ActionOutsidePolicyTarget() {
        String decision = ABACML.Evaluate_ABAC_Decision(
                "alice", "student", "ComputerScience", 3,
                "STUDENT_GRADES", "alice", "ComputerScience", 2,
                "DELETE",
                "campus", 10);
        assertEquals("NotApplicable", decision);
    }
}
